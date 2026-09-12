import os
import zipfile
from pathlib import Path

def create_submission_zip(source_dir: Path, output_zip_path: Path):
    '''
    Packages code/ into code.zip excluding unnecessary directories.
    '''
    exclude_dirs = {'__pycache__', '.pytest_cache', '.git', 'venv', 'env', '.env'}
    exclude_extensions = {'.pyc', '.pyo', '.pyd'}
    
    with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if any(file.endswith(ext) for ext in exclude_extensions):
                    continue
                file_path = Path(root) / file
                arcname = file_path.relative_to(source_dir.parent)
                zf.write(file_path, arcname)
    print(f'Created submission zip: {output_zip_path}')
