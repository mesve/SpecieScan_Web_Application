"""
Setup script for SpecieScan Web Application
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README if it exists
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else "SpecieScan Web Application for ZooMS Analysis"

setup(
    name="specie-scan-web",
    version="4.2.0",
    description="Web-based interface for ZooMS (Zooarchaeology Mass Spectrometry) analysis",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="SpecieScan Development Team",
    author_email="specie_scan@example.com",
    url="https://github.com/mesve/SpecieScan_Web_Application",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        '': [
            'static/css/*.css',
            'static/js/*.js',
            'templates/*.html',
            'reference_databases/*.csv',
            'reference_databases/*.md',
        ],
    },
    install_requires=[
        'Flask>=2.3.0',
        'Werkzeug>=2.3.0',
        'rpy2>=3.5.0',
        'pandas>=2.1.0',
        'numpy>=1.25.0',
        'plotly>=5.17.0',
        'celery>=5.3.0',
        'redis>=5.0.0',
        'pathlib2>=2.3.7',
        'Pillow>=10.1.0',
    ],
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'black>=23.0.0',
            'flake8>=6.0.0',
        ],
    },
    entry_points={
        'console_scripts': [
            'specie-scan=specie_scan:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Scientific/Engineering :: Bio-Informatics',
        'Topic :: Scientific/Engineering :: Chemistry',
    ],
    python_requires='>=3.7',
    zip_safe=False,
)