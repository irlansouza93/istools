# -*- coding: utf-8 -*-
"""
conversor_etl_edgv_300_to_edgv_topo_145.py — Script Standalone de Referência

Versão CLI standalone do conversor ETL EDGV 3.0 v1.1.6 → EDGV Topo v1.4.5.
A lógica principal foi migrada para o plugin ISTools em:
  - converter_logic.py (classe EDGVETLConverter)
  - processing/edgv_etl_topo_algorithm.py (algoritmo de processamento)

Este arquivo é mantido como referência de desenvolvimento.
NÃO é utilizado pelo plugin em runtime.

Autor: Irlan Souza, 2° Sgt Exército Brasileiro
Email: irlansouza193@gmail.com
GitHub: https://github.com/irlansouza93

NOTA: A lógica completa (174 classes, filtros semânticos, mapeamento N-to-N,
      tradução de domínios, e auditoria V22 de fidelidade) foi integrada ao
      módulo converter_logic.EDGVETLConverter do plugin ISTools v1.5.0.
"""

# TODO: Este script pode ser restaurado para uso CLI/batch caso necessário.
# A implementação original executava a conversão diretamente via psycopg2/PyQGIS
# sem depender da interface de processamento do QGIS.

print("conversor_etl_edgv_300_to_edgv_topo_145.py")
print("Versão CLI de referência — lógica migrada para converter_logic.py (plugin ISTools)")
print("Consulte: https://github.com/irlansouza93/istools")
