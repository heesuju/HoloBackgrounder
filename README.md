# GIF to MP4 Processor

A PyQt6-based desktop application that converts GIF and WEBM files into MP4 format. It includes features for background color replacement, frame padding, and looping the resulting video.

## Features

- **Drag and Drop Interface**: Easily import your `.gif` or `.webm` files.
- **Background Replacement**: Replace transparent or solid backgrounds with a specific hex color (e.g., `#ffffff`) by adjusting the color matching threshold.
- **Looping**: Extend the duration of the MP4 by looping the input video a specific number of times.
- **Frame Padding**: Duplicate the last frame to prevent playback skipping on some hardware players.

## Setup

This project uses a Python virtual environment to manage dependencies.

1. **Clone the repository** (or navigate to the project directory):
   ```bash
   cd path/to/rmbg
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**:
   - On Windows:
     ```bash
     .venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source .venv/bin/activate
     ```

4. **Install Dependencies**:
   Install the required Python packages (PyQt6, OpenCV, NumPy, and Pillow):
   ```bash
   pip install PyQt6 opencv-python numpy Pillow
   ```

## Running the Application

Once the virtual environment is activated and the dependencies are installed, you can start the application by running:

```bash
python app.py
```

This will launch the desktop GUI where you can drag and drop your media files and process them.
