# ColorAnalyzer Mobile User Manual

## Overview

ColorAnalyzer Mobile is an offline Android app for comparing color change between two frames or two videos. It is designed to work without internet access once installed.

The app analyzes three roles:

- `control_min`
- `control_max`
- `sample`

Each role can use either a video input or a pair of images. All three roles must use the same input type in a single analysis run.

## Main Screen

The app screen has four main areas:

- Analysis Settings
- Inputs By Role
- Run button and status message
- Results table and error message area

## Analysis Settings

### Duration

Enter the analysis duration as `hh:mm:ss`.

- Hours, minutes, and seconds are entered separately.
- Duration must be greater than zero.

### Control Min and Control Max

These fields are optional calibration targets.

- Leave both blank if you do not want calibration.
- Enter both values if you want the sample result interpolated between them.
- Do not enter only one of the two fields.

## Inputs By Role

Each role section contains a video option and an image-pair option.

### Option 1: Video

Use this when your source is a single video file.

- Tap `Pick Video`.
- Choose an `.mp4`, `.mov`, `.avi`, or `.mkv` file.
- The app uses the selected video for both start and end frame extraction.

### Option 2: Frame Images

Use this when you already have a first frame image and a last frame image.

- Tap `Pick Frame 1` and select the start image.
- Tap `Pick Last Frame` and select the end image.
- The app compares the two images directly.

You must choose one option only for each role. Do not mix a video with frame images for the same role.

## ROI Selection

For image-pair input, each frame preview lets you draw a region of interest.

- Touch and drag on the image preview to draw a rectangle.
- The app shows the ROI as `x,y,w,h` under the preview.
- Tap `Clear ROI` to remove the selection.

If no ROI is drawn, the app uses the full image.

ROI rules:

- The start frame and end frame for a role should have matching dimensions.
- If ROI width or height is `0`, the app expands that edge to the remaining image area.
- If all ROI values are empty or unset, the full frame is used.

## Running an Analysis

After setting the duration and selecting inputs for all three roles:

1. Tap `Run Analysis`.
2. Wait for the status to change from `Running analysis...` to `Complete` or `Error`.
3. Review the results table and any error text below it.

## Results Table

The results table shows one row for each role.

Columns:

- `Role` - the role name
- `Delta E` - the color difference scalar
- `Rate` - Delta E divided by the duration
- `Prediction` - calibrated target value, if calibration is enabled

If calibration is not enabled, the `Prediction` column shows `-`.

## Calibration Behavior

If both calibration targets are entered, the app uses the control roles to interpolate a target for the sample.

- `control_min` is mapped to the first target value.
- `control_max` is mapped to the second target value.
- `sample` is interpolated between them using the measured rates.

Calibration requires all three roles to be present.

## Supported File Types

Video selection accepts:

- `.mp4`
- `.mov`
- `.avi`
- `.mkv`

Image selection accepts:

- `.png`
- `.jpg`
- `.jpeg`
- `.bmp`
- `.webp`

## Troubleshooting

### The app says a role is missing input

Make sure each of the three roles has either a video or a frame-image pair selected.

### The app says you mixed input types

All three roles must use the same input type in one run. Use either all videos or all frame image pairs.

### Calibration error

If you enter calibration values, both fields must be filled and they must not be identical.

### Image dimension error

The start and end images for a role must have the same size.

### File picker does not open

On some Android builds, file access permissions may be restricted. Grant the requested storage or media permissions when prompted.

### App fails to launch

If the app crashes during startup, check `startup_crash.log` in the app's working directory or device storage, if available.

## Practical Workflow

### Video workflow

1. Enter the duration.
2. Leave calibration blank, or enter both calibration targets.
3. For each role, tap `Pick Video` and choose a file.
4. Tap `Run Analysis`.

### Image-pair workflow

1. Enter the duration.
2. Leave calibration blank, or enter both calibration targets.
3. For each role, tap `Pick Frame 1` and `Pick Last Frame`.
4. Draw ROIs if needed.
5. Tap `Run Analysis`.

## Notes

- The app is fully offline.
- The UI is designed for Android touch input.
- Results appear directly inside the app after analysis finishes.