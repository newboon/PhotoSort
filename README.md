# PhotoSort

A simple and fast desktop application for sorting JPG and RAW photos into multiple folders.

![PhotoSort Screenshot](./images/photosort_main.png)

---

## Features

*   Quickly load JPG or RAW photo folders.
*   Optionally pair and move RAW files with JPGs.
*   Supports RAW-only workflow.
*   Sort photos into up to 3 folders using keys `1`, `2`, `3`.
*   Single image view with Zoom (Fit, 100%, 200%) and Pan.
*   Grid views (2x2, 3x3) for faster scanning (F1, F2, F3).
*   Minimap for easy navigation when zoomed.
*   Undo/Redo support (`Ctrl+Z`, `Ctrl+Y`).
*   Displays basic EXIF information.
*   Customizable settings (Language, Theme, Date Format, RAW Strategy, Panel Position).

---

## Download & Run

1.  Go to the **[Releases](https://github.com/newboon/PhotoSort/releases)** page.
2.  Download the `PhotoSort_vX.X.X.zip` file from the latest release.
3.  Extract the zip file.
4.  Run `PhotoSort.exe`. No installation needed.

**⚠️ Note on Windows Defender:** Defender might show a false positive warning (e.g., `Trojan:Win32/Sabsik.FL.A!ml`). This is common for apps built with tools like Nuitka/PyInstaller and is safe. You may need to add an exception in Defender.

---

## Basic Usage

1.  Load a folder using the 'Load JPG' or 'Load RAW' button.
2.  (Optional) Link a RAW folder if needed.
3.  Click the 'Folder Path' labels next to `1`, `2`, `3` to set your destination folders.
4.  Use `WASD` or `Arrow Keys` to navigate photos.
5.  Press `1`, `2`, or `3` to move the current photo to the corresponding folder.
6.  Use `F1`, `F2`, `F3` to switch view modes.

---

## License

This project is licensed under the **MIT License**. See the `LICENSE` file for details.

---

## Support

Found a bug or have a suggestion? Please open an **[Issue](https://github.com/newboon/PhotoSort/issues)**.