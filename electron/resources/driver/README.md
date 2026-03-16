# OBS VirtualCam Driver

To enable the virtual camera feature (webcam sharing), place the **OBS VirtualCam** 64-bit
DirectShow filter in this folder:

```
electron/resources/driver/obs-virtualcam-module64.dll
```

## How to get the file

1. Download **OBS Studio** installer from https://obsproject.com/download
2. Install it (or extract it with 7-Zip)
3. Find `obs-virtualcam-module64.dll` inside the OBS installation folder:
   ```
   C:\Program Files\obs-studio\data\obs-plugins\win-dshow\
   ```
4. Copy that file into this folder.

> **Note:** OBS Studio itself does NOT need to be running. The my-hards app registers
> the driver automatically via `regsvr32` the first time you enable webcam sharing.
> A single UAC (admin) prompt will appear. After that, Teams and other apps will see
> **"OBS Virtual Camera"** in their camera list.

## Uninstalling the driver

Run in an elevated Command Prompt:

```bat
regsvr32 /u "path\to\obs-virtualcam-module64.dll"
```
