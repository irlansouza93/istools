# 🛠️ ISTools Plugin for QGIS

<div align="center">

<img src="icons/icon_istools.png" width="150">

**Complete Geoinformation Suite: Advanced Vectorization, PostGIS and EDGV 3.0 ETL**

<div align="center">
  
🌐 **[🚀 VISIT OUR OFFICIAL WEBSITE - CLICK HERE! 🚀](https://irlansouza93.github.io/istools-website/)**

*Discover more plugins, tutorials and exclusive resources for QGIS!*

</div>

[![QGIS Version](https://img.shields.io/badge/QGIS-3.10+-brightgreen.svg)](https://qgis.org)
[![Version](https://img.shields.io/badge/Version-1.5.3-blue.svg)](https://github.com/irlansouza93/istools)
[![License](https://img.shields.io/badge/License-GPL--3.0-red.svg)](LICENSE)
[![Language](https://img.shields.io/badge/Language-Python-yellow.svg)](https://python.org)

*Enhance your QGIS workflow with professional editing and database management tools.*

</div>

---

## 🌟 Overview

**ISTools** has evolved! Originally a set of vectorization tools, it is now a **Full Geoinformation Suite**. Developed for QGIS, the plugin is designed to optimize the productivity of cartographers, GIS analysts, and data administrators, integrating everything from fine geometric editing to complex PostGIS database management.

Its modern architecture handles large geospatial datasets and precision-demanding workflows while maintaining an intuitive, native interface.

---

## ✨ Key Features

### 📐 Vectorization Suite (Core)
Fast tools for geometry manipulation:
- **🔗 Extend Lines**: Intelligently extend line features to the nearest target (Smart Snapping).
- **📐 Polygon Generator**: Create polygon areas from point clouds with rigorous validation.
- **📍 Point on Surface**: Ensure representative centroids are created inside complex polygons.
- **✂️ Intersection Line**: Automatically create vertices at crossings to maintain topological integrity.
- **Smooth Simplifier**: Reduce vertices in selected lines using a fine, undoable tolerance (Ctrl+Z).

### 🗄️ Database Management (PostGIS)
- **⚡ PostGIS Manager**: Unified interface for fast SQL execution, table maintenance, and direct spatial analysis.
- **📥 Base Importer (SHP to DB)**: Optimized tool for mass Shapefile loading directly into PostGIS with assisted mapping.

### ⚡ Processing Pipelines (ETL)
- **🏗️ EDGV 3.0 ETL**: Specialized module to convert legacy data to the EDGV 3.0 standard (Brazilian Army Geospatial Vector Data Specification).

### 🛰️ External applications
- **[TiffTools Pro](https://irlansouza93.github.io/istools-website/tifftools/)**: Standalone Windows application for compressing and reprojecting TIFF files with the GDAL tools installed by QGIS. It is intended to make very large imagery easier to handle, including on computers with limited memory. The executable is not bundled with the plugin; ISTools only provides a shortcut to its official download and user guide.

---

## 📥 Installation

1. Open **QGIS**.
2. Go to **Plugins** > **Manage and Install Plugins**.
3. Search for **ISTools** or install from the ZIP file in the [Release](https://github.com/irlansouza93/istools/releases) section.

---

## 📋 Requirements

- 🖥️ **QGIS**: Version 3.10 or superior.
- 🐍 **Python**: 3.7+ (Modern QGIS standard).
- 🗄️ **PostGIS**: Required for database and ETL modules.

---

## 🗺️ Contribution

Contributions are vital to ISTools' growth! If you've found a bug or have a strategic suggestion:
1. **Fork** the official project.
2. Create a **Branch** for your update (`git checkout -b feature/new_tool`).
3. Open a **Pull Request** detailing your changes.

---

## 📄 License

This project is licensed under the **GPL-v3.0** license - see the [LICENSE](LICENSE) file for full transparency.

---

<div align="center">

**Developed by Irlan Souza**
*2nd Sgt of the Brazilian Army*

[GitHub](https://github.com/irlansouza93) | [LinkedIn](https://www.linkedin.com/in/irlansouza93/)

</div>
