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
#   jpg|<원본>|<결과>|<품질>    JPG 로 줄여 남긴다 (한 판을 다 남기려고)
#   shot|<창 제목 일부>|<결과>[|x0|y0|x1|y1]
#                                그 창을 찍어 PNG 로 저장한다 (속만, 테두리·제목줄 빼고).
#                                네 수를 주면 그 자리만 잘라 저장한다 → 「OK <창 가로> <창 세로>」
#   bye                          끝낸다
# 시킨 것마다 「OK…」 또는 「ERR <까닭>」 한 줄을 내놓고, 그 다음 「<<END>>」 를 내놓는다.
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
# 창 찍기 — `tools/창사진.ps1` 과 같은 PrintWindow 지만 **창을 앞으로 끌어올리지 않는다.**
# 실전에서는 계속 찍어야 하므로 초점을 뺏으면 안 된다. PW_RENDERFULLCONTENT(2) 로 가려진 창도 그린다.
# PW_CLIENTONLY(1) 을 같이 줘서 제목줄·테두리를 뺀다 — 창 프로젝터는 속이 곧 게임 화면이다.
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Shot {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  public struct RECT { public int L, T, R, B; }
  public static IntPtr Find(string title) {
    IntPtr got = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      if (!IsWindowVisible(h) || IsIconic(h)) return true;
      StringBuilder sb = new StringBuilder(512);
      GetWindowText(h, sb, 512);
      if (sb.ToString().Contains(title)) { got = h; return false; }
      return true;
    }, IntPtr.Zero);
    return got;
  }
}
"@
[Shot]::SetProcessDPIAware() | Out-Null
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

function Do-Shot([string]$title, [string]$dst, $box) {
    $hwnd = [Shot]::Find($title)
    if ($hwnd -eq [IntPtr]::Zero) { throw "그런 창이 없다(또는 최소화됨): $title" }
    $r = New-Object Shot+RECT
    [void][Shot]::GetClientRect($hwnd, [ref]$r)
    $w = $r.R - $r.L; $h = $r.B - $r.T
    if ($w -lt 8 -or $h -lt 8) { throw "창 속이 너무 작다: ${w}x${h}" }
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    try {
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        try {
            $dc = $g.GetHdc()
            $ok = [Shot]::PrintWindow($hwnd, $dc, 3)   # 1 속만 | 2 가려져도 그리기
            $g.ReleaseHdc($dc)
        } finally { $g.Dispose() }
        if (-not $ok) { throw "창을 못 그렸다: $title" }
        # 까만 띠를 여기서 잘라 낸다 — 파이썬에서 자르고 PNG 를 다시 쓰면 0.36초가 더 든다.
        if ($null -ne $box) {
            $x0 = [int]$box[0]; $y0 = [int]$box[1]; $x1 = [int]$box[2]; $y1 = [int]$box[3]
            if ($x0 -lt 0 -or $y0 -lt 0 -or $x1 -gt $w -or $y1 -gt $h -or $x1 -le $x0 -or $y1 -le $y0) {
                throw "자를 자리가 창 속(${w}x${h})을 벗어난다: $x0,$y0,$x1,$y1"
            }
            $rect = New-Object System.Drawing.Rectangle $x0, $y0, ($x1 - $x0), ($y1 - $y0)
            $cut = $bmp.Clone($rect, $bmp.PixelFormat)
            try { $cut.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png) } finally { $cut.Dispose() }
        } else {
            $bmp.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png)
        }
    } finally { $bmp.Dispose() }
    # 창 속 크기를 같이 알려 준다 — 창 크기가 바뀌면 잘라 낼 자리를 다시 찾아야 한다.
    "OK {0} {1}" -f $w, $h
}

function Do-Jpg([string]$src, [string]$dst, [int]$q) {
    # 한 판을 다 남기려면 PNG 는 너무 크다 (2448x1377 한 장 5MB × 800장 = 4GB).
    # JPG 로 남기면 한 장 0.4MB 다. 검사용 대전 사진들도 원래 JPG 다.
    $enc = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
           Where-Object { $_.MimeType -eq 'image/jpeg' }
    $ps = New-Object System.Drawing.Imaging.EncoderParameters 1
    $ps.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
        [System.Drawing.Imaging.Encoder]::Quality, [long]$q)
    $b = [System.Drawing.Bitmap]::FromFile($src)
    try { $b.Save($dst, $enc, $ps) } finally { $b.Dispose(); $ps.Dispose() }
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
            'jpg'   { Do-Jpg $p[1] $p[2] ([int]$p[3]); Say 'OK' }
            'shot'  { Say (Do-Shot $p[1] $p[2] $(if ($p.Count -ge 7) { $p[3..6] } else { $null })) }
            'bye'   { Say 'OK'; Say '<<END>>'; exit 0 }
            default { Say ("ERR 모르는 말: " + $p[0]) }
        }
    } catch {
        Say ("ERR " + ($_.Exception.Message -replace '[\r\n]+', ' '))
    }
    Say '<<END>>'
}
