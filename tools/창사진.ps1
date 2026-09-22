# 창 사진 찍기 — 창(gui.py)을 실제로 띄운 뒤 그 창만 사진으로 찍는다.
#
#   powershell -ExecutionPolicy Bypass -File tools\창사진.ps1 -Out 창.png
#   powershell -ExecutionPolicy Bypass -File tools\창사진.ps1 -Info     (위치·크기만)
#
# 왜 있나: 가짜 tkinter 점검은 "안 터진다" 까지만 본다. 글자 잘림 · 마우스로
# 안 골라짐 · 오른쪽 잘림은 **창을 실제로 띄워 사진으로 봐야** 보였다
# (docs/이어받기.md §5-35~43). 창을 고치면 띄워서 찍고, 사진을 열어 본다.
#
# 다른 창에 가려져 있어도 PrintWindow 로 **그 창만** 그린다 (화면 전체를 안
# 찍으므로 사용자의 다른 창이 찍히지 않는다). 윈도우 전용, 바깥 라이브러리 없음.
# ! UTF-8 BOM 으로 저장해야 한다 — PowerShell 5.1 이 BOM 없는 한글을 깨뜨린다.
param([string]$Title = "무엇을 둘까", [string]$Out = "창.png", [switch]$Info)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  public struct RECT { public int L, T, R, B; }
}
"@
[W]::SetProcessDPIAware() | Out-Null
$scr = [System.Windows.Forms.Screen]::PrimaryScreen
$found = $null
[W]::EnumWindows({ param($h, $l)
  if ([W]::IsWindowVisible($h)) {
    $sb = New-Object System.Text.StringBuilder 512
    [W]::GetWindowText($h, $sb, 512) | Out-Null
    if ($sb.ToString().Contains($Title)) { $script:found = $h; return $false }
  }
  return $true }, [IntPtr]::Zero) | Out-Null
"screen: {0}x{1} (작업영역 {2}x{3})" -f $scr.Bounds.Width, $scr.Bounds.Height, $scr.WorkingArea.Width, $scr.WorkingArea.Height
if (-not $found) { "window: 못 찾음"; exit 1 }
$r = New-Object W+RECT
[W]::GetWindowRect($found, [ref]$r) | Out-Null
"window: x={0} y={1} w={2} h={3}" -f $r.L, $r.T, ($r.R - $r.L), ($r.B - $r.T)
if ($Info) { exit 0 }
[W]::ShowWindow($found, 9) | Out-Null
[W]::SetForegroundWindow($found) | Out-Null
Start-Sleep -Milliseconds 600
[W]::GetWindowRect($found, [ref]$r) | Out-Null
$w = $r.R - $r.L; $h = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
# 다른 창에 가려져도 그 창만 그리게 한다 (PW_RENDERFULLCONTENT = 2)
$dc = $g.GetHdc(); $ok = [W]::PrintWindow($found, $dc, 2); $g.ReleaseHdc($dc)
if (-not $ok) { $g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size $w, $h)) }
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
"saved: $Out"
