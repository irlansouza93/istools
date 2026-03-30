# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Intelligent EDGV 3.0 v1.1.6 ETL
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                               -------------------
        begin                : 2026-03-22
        git sha              : $Format:%H$
        copyright            : (C) 2025 by Irlan Souza, 2° Sgt Brazilian Army
        email                : irlansouza193@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
from typing import Any, Optional

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFile,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterString,
    QgsProcessingParameterEnum
)

from ..edgv_300_shp_to_postgis_logic import (
    MappingRules,
    GeometricAttributeMapper,
    ShapefileReader,
    SqlScriptWriter
)

class EDGV300ShpToPostgisAlgorithm(QgsProcessingAlgorithm):
    """
    Algoritmo para conversão inteligente de Shapefiles para o padrão EDGV 3.0 (PostGIS).
    """
    
    INPUT_DIR = "INPUT_DIR"
    RECURSIVE = "RECURSIVE"
    OUTPUT_MODE = "OUTPUT_MODE"
    SCHEMA_NAME = "SCHEMA_NAME"
    OUTPUT_SQL = "OUTPUT_SQL"
    SERVER_CONN = "SERVER_CONN"
    TARGET_DB = "TARGET_DB"

    def name(self) -> str:
        return "shp_to_postgis_edgv300"

    def displayName(self) -> str:
        return "Conversor Inteligente SHP para PostGIS (EDGV 3.0 v1.1.6)"

    def group(self) -> str:
        return "Ferramentas EDGV"

    def groupId(self) -> str:
        return "ferramentas_edgv"

    def shortHelpString(self) -> str:
        return (
            "Este algoritmo realiza a migração de dados vetoriais em formato Shapefile para o banco de dados PostGIS, "
            "aderindo às especificações da **EDGV 3.0 v1.1.6**.\n\n"
            "Modos de Saída:\n"
            "- **Arquivo SQL**: Gera um script .sql com comandos INSERT (ideal para backups ou execução manual).\n"
            "- **Banco de Dados (Direto)**: Insere os dados diretamente em um banco PostGIS existente.\n\n"
            "Política de Transação (modo Direto):\n"
            "- Cada arquivo Shapefile é tratado como uma unidade de transação independente.\n"
            "- Se a inserção de um arquivo falhar, o rollback afeta apenas esse arquivo.\n"
            "- Os demais arquivos continuam sendo processados normalmente.\n\n"
            "Principais Funcionalidades:\n"
            "- Mapeamento automático de 174 classes master.\n"
            "- Tradução automática de valores de domínio.\n"
            "- Tratamento de geometrias e sufixos (_a, _l, _p).\n"
            "- Relatório de inconsistências em CSV.\n"
            "- CSV de auditoria de erros por arquivo.\n\n"
            "<b>Autor:</b> Irlan Souza\n"
            "<b>Email:</b> <a href=\"mailto:irlansouza193@gmail.com\">irlansouza193@gmail.com</a>\n"
            "<b>GitHub:</b> <a href=\"https://github.com/irlansouza93\">https://github.com/irlansouza93</a>\n\n"
            "<b>🌐 <a href=\"https://irlansouza93.github.io/istools-website/\">🚀VISITE NOSSO SITE OFICIAL - CLIQUE AQUI! 🚀</a></b>"
        )

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        from qgis.core import QgsSettings
        
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_DIR,
                "Diretório raiz dos Shapefiles",
                behavior=QgsProcessingParameterFile.Folder
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.RECURSIVE,
                "Buscar subpastas recursivamente?",
                defaultValue=True
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.OUTPUT_MODE,
                "Modo de Saída",
                options=["Arquivo SQL", "Banco de Dados (PostGIS Direto)"],
                defaultValue=0
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.SCHEMA_NAME,
                "Esquema de destino",
                defaultValue="edgv"
            )
        )

        # Parâmetros para Modo SQL
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_SQL,
                "Arquivo SQL de Saída (apenas para modo SQL)",
                "SQL Files (*.sql)",
                optional=True
            )
        )

        # Parâmetros para Modo Banco
        settings = QgsSettings()
        settings.beginGroup("PostgreSQL/servers")
        servers = settings.childGroups()
        settings.endGroup()

        self.addParameter(
            QgsProcessingParameterEnum(
                self.SERVER_CONN,
                "Servidor PostGIS (apenas para modo Direto)",
                options=servers,
                defaultValue=0 if servers else -1,
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.TARGET_DB,
                "Banco de Dados Destino (apenas para modo Direto)",
                defaultValue="geobase",
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFile(
                "REPORT_DIR",
                "Pasta para Relatório de Inconsistências",
                behavior=QgsProcessingParameterFile.Folder,
                optional=True
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        import csv
        from qgis.core import QgsSettings
        
        input_dir = self.parameterAsFile(parameters, self.INPUT_DIR, context)
        recursive = self.parameterAsBool(parameters, self.RECURSIVE, context)
        output_mode = self.parameterAsInt(parameters, self.OUTPUT_MODE, context) # 0=SQL, 1=DB
        schema_name = self.parameterAsString(parameters, self.SCHEMA_NAME, context)
        report_dir = self.parameterAsFile(parameters, "REPORT_DIR", context)
        output_sql = None

        if not os.path.exists(input_dir):
            raise QgsProcessingException(f"O diretório de entrada não existe: {input_dir}")

        feedback.pushInfo("Lendo regras de mapeamento EDGV 3.0 v1.1.6...")
        try:
            mapping_rules = MappingRules()
        except Exception as e:
            raise QgsProcessingException(f"Erro ao carregar mapeamento: {str(e)}")

        # Preparar Escritor e Diretório de Auditoria
        writer = None
        
        if output_mode == 0:
            # MODO SQL
            output_sql = self.parameterAsFileOutput(parameters, self.OUTPUT_SQL, context)
            if not output_sql:
                raise QgsProcessingException("O caminho do arquivo SQL de saída precisa ser definido.")
            auditoria_dir = report_dir if report_dir else os.path.dirname(output_sql)
            from ..edgv_300_shp_to_postgis_logic import SqlScriptWriter
            writer = SqlScriptWriter(output_sql, schema_name=schema_name)
        else:
            # MODO BANCO DIRETO
            server_idx = self.parameterAsInt(parameters, self.SERVER_CONN, context)
            target_db = self.parameterAsString(parameters, self.TARGET_DB, context)
            
            auditoria_dir = report_dir if report_dir else os.path.join(os.path.expanduser("~"), "Documents")
            
            settings = QgsSettings()
            settings.beginGroup("PostgreSQL/servers")
            servers = settings.childGroups()
            if server_idx < 0 or server_idx >= len(servers):
                raise QgsProcessingException("Nenhum servidor PostGIS válido selecionado.")
            
            server_name = servers[server_idx]
            settings.endGroup()
            
            settings.beginGroup(f"PostgreSQL/servers/{server_name}")
            conn_params = {
                "host": settings.value("host", "localhost"),
                "port": settings.value("port", "5432"),
                "user": settings.value("username", "postgres"),
                "password": settings.value("password", ""),
                "authcfg": settings.value("authcfg", "")
            }
            settings.endGroup()
            
            feedback.pushInfo(f"Conectando ao banco '{target_db}' no servidor '{server_name}'...")
            from ..edgv_300_shp_to_postgis_logic import PostGISBatchWriter
            try:
                writer = PostGISBatchWriter(conn_params, target_db, schema_name=schema_name)
            except Exception as e:
                raise QgsProcessingException(f"Falha na conexão com o banco: {e}")

        if not auditoria_dir or not os.path.exists(auditoria_dir):
             auditoria_dir = input_dir # Fallback final

        mapper = GeometricAttributeMapper(mapping_rules, auditoria_dir)
        
        all_shapefiles = []
        if recursive:
            for root, dirs, files in os.walk(input_dir):
                for file in files:
                    if file.lower().endswith(".shp"):
                        all_shapefiles.append(os.path.join(root, file))
        else:
            reader = ShapefileReader(input_dir)
            all_shapefiles = reader.get_shapefiles()

        if not all_shapefiles:
            raise QgsProcessingException("Nenhum arquivo Shapefile (.shp) encontrado no diretório selecionado.")

        feedback.pushInfo(f"Encontrados {len(all_shapefiles)} arquivos para processamento.")
        
        # --- Estrutura de Resumo por Arquivo ---
        file_results = []  # [{file, features_read, features_inserted, status, error}]
        total_features_read = 0
        total_features_inserted = 0
        total_files_ok = 0
        total_files_error = 0
        
        step = 100.0 / len(all_shapefiles)
        
        for i, shp_file in enumerate(all_shapefiles):
            if feedback.isCanceled():
                break
                
            filename = os.path.basename(shp_file)
            shp_class_name, _ = os.path.splitext(filename)
            
            feedback.pushInfo(f"Processando ({i+1}/{len(all_shapefiles)}): {filename}")
            
            file_info = {
                "file": filename,
                "features_read": 0,
                "features_inserted": 0,
                "status": "ok",
                "error": ""
            }
            
            try:
                file_reader = ShapefileReader(os.path.dirname(shp_file))
                records = file_reader.read_records(shp_file)
                file_info["features_read"] = len(records)
                total_features_read += len(records)
                
                batch_records = []
                real_class_name = shp_class_name[:-2] if shp_class_name[-2:].lower() in ("_a", "_l", "_p") else shp_class_name
                
                for shape_rec in records:
                    pg_rec = mapper.map_record(real_class_name, shp_class_name, shape_rec)
                    if pg_rec:
                        batch_records.append(pg_rec)
                
                file_info["features_inserted"] = len(batch_records)
                total_features_inserted += len(batch_records)
                
                if batch_records:
                    writer.write_inserts(batch_records)
                    if output_mode == 1:
                        # Política de transação: commit por arquivo
                        writer.commit()
                
                total_files_ok += 1
                    
            except Exception as e:
                file_info["status"] = "error"
                file_info["error"] = str(e)
                total_files_error += 1
                
                feedback.reportError(f"❌ ROLLBACK do arquivo '{filename}': {str(e)}")
                
                # Rollback por arquivo no modo banco
                if output_mode == 1 and hasattr(writer, 'rollback'):
                    try:
                        writer.rollback()
                    except Exception:
                        pass
                
            file_results.append(file_info)
            feedback.setProgress(int((i + 1) * step))

        writer.close()
        
        # --- Gerar CSV de Auditoria de Erros ---
        error_csv_path = None
        if total_files_error > 0:
            error_csv_path = os.path.join(auditoria_dir, "edgv_etl_erros_por_arquivo.csv")
            try:
                with open(error_csv_path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(["Arquivo", "Feições Lidas", "Feições Inseridas", "Status", "Erro"])
                    for fr in file_results:
                        if fr["status"] == "error":
                            w.writerow([fr["file"], fr["features_read"],
                                       fr["features_inserted"], fr["status"], fr["error"]])
            except Exception:
                error_csv_path = None

        # --- RESUMO FINAL ---
        feedback.pushInfo("\n" + "=" * 50)
        feedback.pushInfo("       RESUMO DA CONVERSÃO EDGV 3.0 v1.1.6")
        feedback.pushInfo("=" * 50)
        
        if output_mode == 0:
            feedback.pushInfo(f"📄 Arquivo SQL gerado: {output_sql}")
        else:
            feedback.pushInfo(f"🗄️ Inserção concluída no banco PostGIS.")
            feedback.pushInfo(f"   Política de transação: por arquivo (rollback individual)")
            
        feedback.pushInfo(f"\n📊 Arquivos processados: {total_files_ok + total_files_error}")
        feedback.pushInfo(f"   ✅ Com sucesso: {total_files_ok}")
        feedback.pushInfo(f"   ❌ Com falha:   {total_files_error}")
        feedback.pushInfo(f"\n📈 Feições lidas:     {total_features_read}")
        feedback.pushInfo(f"   Feições inseridas: {total_features_inserted}")
        
        if total_files_error > 0:
            feedback.pushInfo(f"\n⚠️ Arquivos com erro:")
            for fr in file_results:
                if fr["status"] == "error":
                    feedback.reportError(f"   • {fr['file']}: {fr['error']}")
            if error_csv_path:
                feedback.pushInfo(f"\n📋 Relatório de erros CSV: {error_csv_path}")
                    
        feedback.pushInfo(f"\n📁 Relatório de inconsistências de mapeamento: {auditoria_dir}")
        feedback.pushInfo("=" * 50)

        return {self.OUTPUT_SQL: (output_sql if output_mode == 0 else "Direct Database")}

    def createInstance(self):
        return self.__class__()
