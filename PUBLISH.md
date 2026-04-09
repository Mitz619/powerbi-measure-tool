# Publishing Guide

Step-by-step instructions for maintaining and publishing this package.

---

## First-time setup

### 1. Replace placeholders

Search the repo for `YOUR_USERNAME` and `YOUR_NAME` and replace with your details:
- `pyproject.toml` — GitHub URLs
- `README.md` — GitHub badge URLs
- `LICENSE` — your name and year

### 2. Create accounts

- [GitHub](https://github.com) — for source hosting
- [PyPI](https://pypi.org) — for package distribution
- [TestPyPI](https://test.pypi.org) — for testing uploads (optional but recommended)

### 3. Generate a PyPI API token

1. Log in to pypi.org
2. Go to **Account Settings → API tokens → Add API token**
3. Scope: **Entire account** (or just this project after first upload)
4. Copy the token — you only see it once

### 4. Add the token to GitHub

1. Go to your GitHub repo → **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `PYPI_API_TOKEN`
4. Value: paste the token

---

## Initial upload to PyPI

```bash
# Install build tools
pip install build twine hatchling

# Build
python -m build
# Creates:
#   dist/powerbi_measure_tool-0.1.0.tar.gz
#   dist/powerbi_measure_tool-0.1.0-py3-none-any.whl

# Optional: test on TestPyPI first
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ powerbi-measure-tool

# Upload to real PyPI
twine upload dist/*
# Username: __token__
# Password: paste your API token
```

---

## Push to GitHub

```bash
cd powerbi-measure-tool

git init
git add .
git commit -m "Initial release v0.1.0"

# Create the repo on github.com first (empty, no README)
git remote add origin https://github.com/YOUR_USERNAME/powerbi-measure-tool.git
git branch -M main
git push -u origin main

# Tag and create a GitHub Release
git tag v0.1.0
git push origin v0.1.0
```

Then on GitHub: **Releases → Draft a new release → Choose tag v0.1.0 → Publish release**

The GitHub Action (`.github/workflows/publish.yml`) will automatically build and upload to PyPI on every new version tag.

---

## Releasing a new version

```bash
# 1. Update version in pyproject.toml
#    version = "0.2.0"

# 2. Update CHANGELOG.md with what changed

# 3. Commit
git add pyproject.toml CHANGELOG.md
git commit -m "Release v0.2.0: describe changes"

# 4. Tag and push — GitHub Actions handles the rest
git tag v0.2.0
git push origin main --tags
```

---

## Running tests locally

```bash
pip install -e ".[dev]"   # or: pip install pytest && pip install -e .
pytest tests/ -v
```

---

## Installing from source (for development)

```bash
git clone https://github.com/YOUR_USERNAME/powerbi-measure-tool.git
cd powerbi-measure-tool
pip install -e .
pbi-measure --help
```
