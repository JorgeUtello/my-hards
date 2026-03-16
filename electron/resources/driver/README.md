# Unity Capture Driver

To enable the virtual camera feature (webcam sharing), place the **Unity Capture** 64-bit
DirectShow filter in this folder:

```
electron/resources/driver/UnityCapture64.ax
```

## How to get the file

1. Download the latest release from:
   https://github.com/schellingb/UnityCapture/releases

2. From the zip, extract **`UnityCapture64.ax`** and copy it into this folder.

> **Note:** The my-hards app will register the driver automatically via `regsvr32` the first
> time you enable webcam sharing in the server card. A single UAC (admin) prompt will appear.
> After that, Teams and other apps will see "Unity Video Capture" in their camera list.

## Uninstalling the driver

Run in an elevated Command Prompt:

```bat
regsvr32 /u "path\to\UnityCapture64.ax"
```
