# XRTourGuide Tour Import Scripts

## Overview

This repository contains Python scripts to import tour data into the XRTourGuide platform. The scripts process folder structures containing waypoint information, images, audio, video, PDFs, and other media files.

**Available Scripts:**
- `init_san_nilo.py` - Import "Cammino di San Nilo" tour with automatic audio generation from DOCX files
- `init_unisa.py` - Import "Unisa" tour with support for subtours and nested waypoints

---

## Requirements

### System Requirements

- Python 3.8 or higher
- Django-based XRTourGuide backend (configured and running)
- Piper TTS (for audio generation - only needed for `init_san_nilo.py`)

### Python Dependencies

Install the required Python packages:

```bash
pip install django python-docx piper-tts[all]
```

**Package Details:**
- `django` - Web framework (required by XRTourGuide backend)
- `python-docx` - Read and extract text from Microsoft Word documents
- `piper-tts[all]` - Text-to-speech engine with all language support
- `pathvalidate`

---

## Installation & Setup

### 1. Clone/Download the Scripts

Place the import scripts in your XRTourGuide project root directory:

```
xr_tour_guide/
├── init_san_nilo.py
├── init_unisa.py
├── manage.py
└── ...
```

### 2. Install Python Dependencies

Create and activate a virtual environment (recommended):

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install django python-docx piper-tts[all]
```

### 3. Download Piper Voice Models

For Italian text-to-speech (used in `init_san_nilo.py`), download the Piper voice model files:

**Model:** `it_IT-riccardo-x_low`

**Download Links:**
1. Visit the official Piper voices repository:
   - https://github.com/rhasspy/piper/blob/master/VOICES.md
   - https://huggingface.co/rhasspy/piper-voices/tree/main/it/it_IT/riccardo/x_low

2. Download these two files:
   - `it_IT-riccardo-x_low.onnx` (voice model file)
   - `it_IT-riccardo-x_low.onnx.json` (model configuration)

3. Place both files in your project root directory:

```
xr_tour_guide/
├── it_IT-riccardo-x_low.onnx
├── it_IT-riccardo-x_low.onnx.json
├── init_san_nilo.py
└── ...
```

**Alternative Voice Models:**

For other languages, browse available voices at:
- https://github.com/rhasspy/piper/blob/master/VOICES.md

Examples:
- **English (US):** `en_US-lessac-medium`
- **English (UK):** `en_GB-alan-medium`
- **Spanish:** `es_ES-carlfm-x_low`
- **French:** `fr_FR-siwis-medium`
- **German:** `de_DE-thorsten-medium`

To use a different voice model, update the `VOICE_MODEL` variable in the script:

```python
VOICE_MODEL = "./en_US-lessac-medium.onnx"
```

### 4. Configure Django Settings

Ensure your Django project is properly configured. The scripts expect:

```python
# xr_tour_guide/settings.py
DJANGO_SETTINGS_MODULE = 'xr_tour_guide.settings'
```

### 5. Create Required User Account

Before running the scripts, create a user account in your Django application:

**For `init_san_nilo.py`:**
```python
# The script expects a user with username 'username'
# Change this in the script or create the user:
user=CustomUser.objects.get(username='username')
```

**For `init_unisa.py`:**
```python
# The script expects a user with username 'username'
# Change this in the script or create the user:
user=CustomUser.objects.get(username='username')
```

**Create user via Django shell:**
```bash
python manage.py shell

>>> from xr_tour_guide_core.models import CustomUser
>>> CustomUser.objects.create_user(username='username', email='user@example.com', password='your_password', city='city', description='description', name='name', last_name='last_name')
>>> exit()
```

---

### Script Configuration

**Edit `init_san_nilo.py`:**

```python
# Base path to tour folders
BASE_PATH = "./san_nilo"

# Voice model path (download from Piper voices)
VOICE_MODEL = "./it_IT-riccardo-x_low.onnx"

# User account (create this user first)
user=CustomUser.objects.get(username='username')
```

**Edit `init_unisa.py`:**

```python
# Base path to tour folders
BASE_PATH = "unisa_file"

# User account (create this user first)
user=CustomUser.objects.get(username='username')
```

---

## Running the Scripts

### 1. Run Database Migrations

Ensure your database is up to date:

```bash
python manage.py makemigrations
python manage.py migrate
```

### 2. Create User Accounts

Create the required user accounts (if not already created):

```bash
python manage.py createsuperuser
# Or create via Django shell as shown above
```

### 3. Prepare Your Data

Organize your tour data according to the folder structures shown above.

### 4. Run the Import Scripts

**Import San Nilo Tour:**

```bash
python init_san_nilo.py
```

**Import Unisa Tour:**

```bash
python init_unisa.py
```
---

## Features

### `init_san_nilo.py` Features

- ✅ Automatically extracts text from DOCX files
- ✅ Generates audio narration using Piper TTS
- ✅ Supports multiple media types (images, video, PDF, audio)
- ✅ Sorted waypoint processing (by folder name)
- ✅ Skips duplicate waypoints (updates description if changed)

### `init_unisa.py` Features

- ✅ Supports **subtours** (folders starting with "Interno")
- ✅ Nested waypoint structure
- ✅ Links subtours to main tour automatically
- ✅ Preserves existing tours and waypoints
- ✅ Comprehensive logging

---

## Additional Resources

- **Piper TTS Documentation:** https://github.com/rhasspy/piper
- **Piper Voice Models:** https://github.com/rhasspy/piper/blob/master/VOICES.md
- **Hugging Face Models:** https://huggingface.co/rhasspy/piper-voices
- **Django Documentation:** https://docs.djangoproject.com/
- **python-docx Documentation:** https://python-docx.readthedocs.io/

---

## License

This project uses the BSD License. See the XRTourGuide project for full license details.

---

## Support

For issues or questions:
- Email: isislab.unisa@gmail.com
- GitHub: [XRTourGuide](https://github.com/isislab-unisa/XRTourGuide)

---
