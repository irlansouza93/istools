#/***************************************************************************
#  ISTools - Makefile
#  Professional Geoinformation Toolkit for QGIS
# ***************************************************************************/

PLUGINNAME = istools

# Arquivos fonte Python (todos no mesmo nivel)
PY_FILES = istools.py __init__.py polygon_generator.py \
           bounded_polygon_generator.py extend_lines.py \
           point_on_surface_generator.py intersection_line.py \
           clip_by_frame_logic.py converter_logic.py \
           database_manager_logic.py edgv_300_shp_to_postgis_logic.py \
           load_shape_database_logic.py postgis_to_shp_logic.py \
           shp_to_postgis_logic.py

UI_FILES = gui/*.ui
RESOURCE_FILES = resources.qrc
HELP_DIR = help
TEST_DIR = tests

help:
	@echo "ISTools Makefile (Versao 1.5.0)"
	@echo "-------------------------------"
	@echo "Available commands:"
	@echo "  make compile    - Compile resources and UI files (using pyrcc5)"
	@echo "  make build      - Build the plugin ZIP for release"
	@echo "  make help-html  - Generate help documentation (Sphinx)"
	@echo "  make test       - Run internal tests (using pytest)"
	@echo "  make package    - Full build and package"

compile:
	pyrcc5 -o resources.py resources.qrc

help-html:
	cd help && make html

test:
	pytest tests/

package: compile
	powershell -ExecutionPolicy Bypass -File scripts/create_zip.ps1

.PHONY: help compile help-html test package
