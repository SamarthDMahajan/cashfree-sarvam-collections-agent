"""
Windows-compatible Lambda deployment package builder.
Packages:
- `lambda_handler.py`
- `app/` folder (code and configurations)
Outputs: `dist/lambda_deploy.zip`
"""
import os
import zipfile
import shutil

def build_zip():
    dist_dir = "dist"
    os.makedirs(dist_dir, exist_ok=True)
    zip_path = os.path.join(dist_dir, "lambda_deploy.zip")

    if os.path.exists(zip_path):
        os.remove(zip_path)

    print(f"Creating Lambda deployment artifact: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Add lambda_handler.py
        if os.path.exists("lambda_handler.py"):
            zf.write("lambda_handler.py", arcname="lambda_handler.py")
            print(" + Added lambda_handler.py")

        # 2. Add app package files
        for root, dirs, files in os.walk("app"):
            # Exclude __pycache__
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for file in files:
                if file.endswith((".pyc", ".pyo")):
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.getcwd())
                zf.write(file_path, arcname=arcname)
                print(f" + Added {arcname}")

    size_kb = os.path.getsize(zip_path) / 1024
    print(f"\nLambda deployment package created successfully: {zip_path} ({size_kb:.1f} KB)")
    print("Ready to upload to AWS Lambda 'samarthdmahajan-collections-agent'.")

if __name__ == "__main__":
    build_zip()
