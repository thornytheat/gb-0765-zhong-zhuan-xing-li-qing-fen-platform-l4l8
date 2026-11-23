from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[1] / 'sample_data'
FILES = ('scans.csv', 'legs.csv', 'manifest.csv', 'retags.csv')
CORE_FILES = ('scans.csv', 'legs.csv', 'manifest.csv')
SAMPLE_NAMES = ('dirty', 'clean', 'retag')
VERSION = 'leg-luggage/2'
