# 화면 일꾼 — 파워셸을 **한 번만 켜 두고** 사진 바꾸기·글자 읽기를 계속 시킨다.
#
#   (파이썬 쪽에서 subprocess 로 켜고 stdin 에 한 줄씩 넣는다 — screenread.Worker)
#
# 왜 있나: 사진 한 장을 읽을 때마다 파워셸을 두 번 켰다 (그림 바꾸기 + 글자 읽기).
# 켜는 데만 장당 0.35초씩, 합쳐서 0.79초가 갔다 (2026-09-23 에 잼). 캡처보드 화면을
# 계속 읽으려면 이게 제일 크다. 켜 둔 채로 시키면 그 시간이 한 번으로 줄고, 글자 인식
# 엔진도 한 번만 만들면 된다.
#
# 주고받는 말 — 한 줄에 하나, 부분은 세로줄(|) 로 나눈다:
#   png|<원본>|<결과>            그림을 PNG 로 바꾼다
#   scale|<원본>|<결과>|<배수>   그림을 그만큼 키워 PNG 로 저장한다
#   ocr|<사진>                   글자를 읽어 「<사진>.txt」 에 적는다
#   bye                          끝낸다
# 시킨 것마다 「OK」 또는 「ERR <까닭>」 한 줄을 내놓고, 그 다음 「<<END>>」 를 내놓는다.
# 파이썬은 <<END>> 까지 읽는다 — 그래야 어디서 끊어야 할지 안다.
#
# 걸린 것 (다시 밟지 말 것):
#   - 한글 경로가 깨진다 → 들고나는 글자를 UTF-8 로 못 박는다 (BOM 없는 UTF-8).
#   - 내놓은 줄이 파이썬에 바로 안 간다 → 줄마다 Flush 한다. 안 하면 서로 기다리다 멈춘다.
#   - 글자 인식은 「글자읽기.ps1」 과 **같은 방법**이다. 거기 적힌 함정도 그대로다
#     (Language 따로 불러오기 · Wait 의 true 버리기 · 빈 결과 @(...) 로 감싸기).
# ! UTF-8 BOM 으로 저장해야 한다 — PowerShell 5.1 이 BOM 없는 한글을 깨뜨린다.

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
[void][Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]

$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) {
    $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); [void]$task.Wait(); $task.Result
}
# 글자 인식 엔진은 **한 번만** 만든다 — 시킬 때마다 만들면 켜 둔 보람이 없다.
$eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('ko'))

function Say([string]$s) { [Console]::Out.WriteLine($s); [Console]::Out.Flush() }

function Do-Png([string]$src, [string]$dst) {
    $b = [System.Drawing.Bitmap]::FromFile($src)
    try { $b.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png) } finally { $b.Dispose() }
}

function Do-Scale([string]$src, [string]$dst, [int]$n) {
    $s = [System.Drawing.Bitmap]::FromFile($src)
    try {
        $b = New-Object System.Drawing.Bitmap ($s.Width * $n), ($s.Height * $n)
        try {
            $g = [System.Drawing.Graphics]::FromImage($b)
            try {
                $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $g.DrawImage($s, 0, 0, $b.Width, $b.Height)
            } finally { $g.Dispose() }
            $b.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $b.Dispose() }
    } finally { $s.Dispose() }
}

function Do-Ocr([string]$path) {
    $full = (Resolve-Path -LiteralPath $path).Path
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($full)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $res = Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
        [string[]]$out = @(foreach ($l in $res.Lines) {
            $w = $l.Words | Select-Object -First 1
            $r = $w.BoundingRect
            $x = [int]($r | Select-Object -First 1).X; $y = [int]($r | Select-Object -First 1).Y
            "{0,5},{1,5}  {2}" -f $x, $y, $l.Text
        })
        [IO.File]::WriteAllLines("$full.txt", $out, [Text.Encoding]::UTF8)
    } finally { $stream.Dispose() }
}

Say 'READY'
while ($true) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) { break }
    $line = $line.Trim()
    if ($line -eq '') { continue }
    $p = $line -split '\|'
    try {
        switch ($p[0]) {
            'png'   { Do-Png $p[1] $p[2]; Say 'OK' }
            'scale' { Do-Scale $p[1] $p[2] ([int]$p[3]); Say 'OK' }
            'ocr'   { Do-Ocr $p[1]; Say 'OK' }
            'bye'   { Say 'OK'; Say '<<END>>'; exit 0 }
            default { Say ("ERR 모르는 말: " + $p[0]) }
        }
    } catch {
        Say ("ERR " + ($_.Exception.Message -replace '[\r\n]+', ' '))
    }
    Say '<<END>>'
}
