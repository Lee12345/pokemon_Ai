# 글자 읽기 — 게임 화면 사진 한 장을 윈도우 기본 글자 인식(Windows.Media.Ocr)으로 읽는다.
#
#   powershell -ExecutionPolicy Bypass -File tools\글자읽기.ps1 -Path 사진.png
#
# 결과는 사진 옆 「사진.png.txt」 에 한 줄씩 「x, y  글자」 로 적는다 (x, y 는 그 줄
# 첫 낱말의 왼쪽 위 픽셀). 한 장 약 0.6초 (파워셸 켜는 시간 포함, 2732x2048 원본).
#
# 왜 있나: 게임 화면 사진 읽기(docs/이어받기.md §10 「0. 지금 진행 중」) 의 첫 시험에
# 쓴 것이다. 바깥 라이브러리 없이 윈도우에 들어 있는 것만 쓴다. 한국어 인식 언어가
# 깔려 있어야 한다 (이 컴퓨터에는 한국어 하나뿐이다).
#
# 잰 결과 (2026-09-22, 아이패드 녹화):
#   - 아래 문구 칸(흰 글자·어두운 바탕) 과 큰 숫자(122/215, 29%) 는 정확하다.
#   - 색 바탕 글자는 섞인다 (마폭시→「0}폭시」) → 도감 이름으로 가장 가까운 것에 맞춰야 한다.
#
# 이 스크립트를 만들며 걸린 것 (다시 밟지 말 것):
#   - Windows.Globalization.Language 를 따로 불러와야 한다 (안 하면 형을 못 찾음).
#   - $task.Wait() 의 true 가 결과에 섞여 나온다 → [void] 로 버린다.
#   - $l.Words[0] 이 배열로 나오는 경우가 있다 → Select-Object -First 1.
# ! UTF-8 BOM 으로 저장해야 한다 — PowerShell 5.1 이 BOM 없는 한글을 깨뜨린다.
param([string]$Path)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
[void][Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
$ErrorActionPreference = 'Stop'
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) {
    $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); [void]$task.Wait(); $task.Result
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $Path).Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('ko'))
$res = Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
$out = foreach ($l in $res.Lines) {
    $w = $l.Words | Select-Object -First 1
    $r = $w.BoundingRect
    $x = [int]($r | Select-Object -First 1).X; $y = [int]($r | Select-Object -First 1).Y
    "{0,5},{1,5}  {2}" -f $x, $y, $l.Text
}
[IO.File]::WriteAllLines("$Path.txt", $out, [Text.Encoding]::UTF8)
