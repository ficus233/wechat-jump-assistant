"""Restore the checked-in regression pictures and reports."""
from pathlib import Path
import zipfile

def prepare():
    root=Path(__file__).resolve().parent
    with zipfile.ZipFile(root/'regression-data.zip') as archive:
        for item in archive.infolist():
            target=(root/item.filename).resolve()
            if not target.is_relative_to(root):raise ValueError('Invalid fixture path')
            if not target.exists():archive.extract(item,root)

if __name__=='__main__':prepare()
