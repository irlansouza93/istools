# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Database Manager Logic
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                               -------------------
        begin                : 2026-03-20
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
from pathlib import Path
import psycopg2
from psycopg2 import sql
from qgis.PyQt.QtCore import QSettings
from qgis.core import QgsMessageLog, Qgis


# ========================================================================
#  CONEXÃO
# ========================================================================

def get_db_connection(params, dbname=None):
    """Abre conexão psycopg2 filtrando chaves que o driver não reconhece."""
    conn_params = params.copy()
    if dbname:
        conn_params["dbname"] = dbname
    # authcfg é do QGIS, psycopg2 não sabe o que é
    for key in ("authcfg",):
        conn_params.pop(key, None)
    return psycopg2.connect(**conn_params)


def list_databases(params):
    """Lista bancos de dados no servidor (exclui templates e 'postgres')."""
    conn = get_db_connection(params, "postgres")
    cur = conn.cursor()
    cur.execute(
        "SELECT datname FROM pg_database "
        "WHERE datistemplate = false AND datname != 'postgres' "
        "ORDER BY datname"
    )
    dbs = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return dbs



def get_configured_servers():
    """Retorna os nomes dos servidores PostgreSQL salvos no QgsSettings."""
    settings = QSettings()
    settings.beginGroup("PostgreSQL/servers")
    servers = settings.childGroups()
    settings.endGroup()
    return servers


def get_server_info(conn_name):
    """L? informa??es de um servidor salvo no QgsSettings."""
    settings = QSettings()
    settings.beginGroup(f"PostgreSQL/servers/{conn_name}")
    data = {
        "name": conn_name,
        "host": settings.value("host", ""),
        "port": str(settings.value("port", "5432")),
        "user": settings.value("username", ""),
        "password": settings.value("password", ""),
        "authcfg": settings.value("authcfg", ""),
        "databases": settings.value("databases", ""),
    }
    settings.endGroup()
    return data


def get_server_connection_params(conn_name, db_name=None):
    """Monta par?metros de conex?o psycopg2/QGIS a partir do QgsSettings."""
    data = get_server_info(conn_name)
    if not data["host"] or not data["user"]:
        raise ValueError(f"Configura??o incompleta para o servidor: {conn_name}")

    params = {
        "host": data["host"],
        "port": data["port"],
        "user": data["user"],
        "password": data["password"],
    }
    if data.get("authcfg"):
        params["authcfg"] = data["authcfg"]
    if db_name:
        params["dbname"] = db_name
    return params


def save_server_databases(conn_name, databases):
    """Persiste a lista de bancos encontrada para um servidor."""
    settings = QSettings()
    settings.beginGroup(f"PostgreSQL/servers/{conn_name}")
    settings.setValue("databases", ",".join(databases))
    settings.endGroup()



def refresh_server_databases(conn_name):
    """Atualiza a lista de bancos de um servidor usando conex?o real."""
    params = get_server_connection_params(conn_name)
    databases = list_databases(params)
    save_server_databases(conn_name, databases)
    return databases



def get_server_databases(conn_name, refresh_if_missing=True):
    """Retorna os bancos salvos para um servidor, atualizando se necess?rio."""
    if not conn_name:
        return []
    data = get_server_info(conn_name)
    raw = data.get("databases") or ""
    databases = [db.strip() for db in raw.split(",") if db.strip()]
    if databases:
        return databases
    if refresh_if_missing:
        return refresh_server_databases(conn_name)
    return []



def database_exists(params, db_name):
    """Verifica se um banco existe no servidor."""
    conn = get_db_connection(params, "postgres")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists



def create_database(params, db_name, allow_existing=False):
    """Cria um novo banco no servidor."""
    conn = get_db_connection(params, "postgres")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    exists = cur.fetchone() is not None
    if exists and not allow_existing:
        cur.close()
        conn.close()
        raise ValueError(f"O banco '{db_name}' j? existe.")
    if not exists:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    cur.close()
    conn.close()



def drop_database(params, db_name, if_exists=True):
    """Exclui banco no servidor encerrando sess?es antes."""
    terminate_db_sessions(params, db_name)
    conn = get_db_connection(params, "postgres")
    conn.autocommit = True
    cur = conn.cursor()
    if if_exists:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name)))
    else:
        cur.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(db_name)))
    cur.close()
    conn.close()



def execute_sql_file(params, db_name, sql_path):
    """Executa um arquivo SQL em um banco usando psycopg2."""
    sql_text = Path(sql_path).read_text(encoding='utf-8-sig')
    conn = get_db_connection(params, db_name)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(sql_text)
    cur.close()
    conn.close()



def get_topo_sql_script_paths(base_dir=None):
    """Retorna os scripts SQL oficiais de cria??o do banco Topo 1.4.5."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent / 'scripts' / 'sql_creator_database_edgv'
    else:
        base_dir = Path(base_dir)
    return [
        str(base_dir / 'edgv_300_topo_14.sql'),
        str(base_dir / 'edgv_300_topo_extension_14.sql'),
    ]



def create_topo_database(conn_name, db_name, allow_existing=False):
    """Cria um banco EDGV 3.0 Topo 1.4.5 a partir dos scripts oficiais."""
    params = get_server_connection_params(conn_name)
    create_database(params, db_name, allow_existing=allow_existing)
    for sql_path in get_topo_sql_script_paths():
        execute_sql_file(params, db_name, sql_path)
    try:
        refresh_server_databases(conn_name)
    except Exception as error:
        QgsMessageLog.logMessage(
            f"O banco '{db_name}' foi criado, mas a lista do servidor "
            f"'{conn_name}' não pôde ser atualizada: {error}",
            "ISTools",
            Qgis.Warning,
        )
    return get_server_connection_params(conn_name, db_name)


# ========================================================================
#  SCHEMAS E TABELAS
# ========================================================================

def list_user_schemas(params, db_name):
    """Retorna schemas de usuário ordenados (public/edgv primeiro)."""
    conn = get_db_connection(params, db_name)
    cur = conn.cursor()
    cur.execute("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
          AND schema_name NOT LIKE 'pg_toast%%'
        ORDER BY
          CASE WHEN schema_name = 'public' THEN 0
               WHEN schema_name = 'edgv'   THEN 1
               ELSE 2 END,
          schema_name
    """)
    schemas = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return schemas


def list_spatial_tables(params, db_name, schema_name):
    """Retorna nomes de tabelas com geometria/geografia em um schema."""
    conn = get_db_connection(params, db_name)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT f_table_name FROM geometry_columns
        WHERE f_table_schema = %s
        UNION
        SELECT DISTINCT f_table_name FROM geography_columns
        WHERE f_table_schema = %s
    """, (schema_name, schema_name))
    tables = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return tables


def count_tables_for_reset(params, db_name, schema_name, mode="all"):
    """Conta quantas tabelas serão afetadas pelo reset (preview)."""
    conn = get_db_connection(params, db_name)
    cur = conn.cursor()
    if mode == "all":
        cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname = %s", (schema_name,))
    else:
        cur.execute("""
            SELECT count(*) FROM pg_tables t
            WHERE schemaname = %s AND EXISTS (
                SELECT 1 FROM geometry_columns gc
                WHERE gc.f_table_schema = t.schemaname AND gc.f_table_name = t.tablename
                UNION
                SELECT 1 FROM geography_columns ggc
                WHERE ggc.f_table_schema = t.schemaname AND ggc.f_table_name = t.tablename
            )
        """, (schema_name,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


# ========================================================================
#  RESET
# ========================================================================

def reset_schema_data(params, db_name, schema_name, mode="all"):
    """
    Apaga dados de tabelas de um schema.
    mode: 'all' ou 'spatial'.
    Retorna quantidade de tabelas afetadas.
    """
    conn = get_db_connection(params, db_name)
    conn.autocommit = True
    cur = conn.cursor()

    if mode == "all":
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s", (schema_name,))
    else:
        cur.execute("""
            SELECT tablename FROM pg_tables t
            WHERE schemaname = %s AND EXISTS (
                SELECT 1 FROM geometry_columns gc
                WHERE gc.f_table_schema = t.schemaname AND gc.f_table_name = t.tablename
                UNION
                SELECT 1 FROM geography_columns ggc
                WHERE ggc.f_table_schema = t.schemaname AND ggc.f_table_name = t.tablename
            )
        """, (schema_name,))

    tables = [row[0] for row in cur.fetchall()]
    if not tables:
        cur.close()
        conn.close()
        return 0

    qualified_tables = [
        sql.SQL("{}.{}").format(
            sql.Identifier(schema_name),
            sql.Identifier(table_name),
        )
        for table_name in tables
    ]
    cur.execute(
        sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
            sql.SQL(", ").join(qualified_tables)
        )
    )

    cur.close()
    conn.close()
    return len(tables)


# ========================================================================
#  SESSÕES
# ========================================================================

def terminate_db_sessions(params, db_name):
    """Encerra sessões ativas em um banco."""
    conn = get_db_connection(params, "postgres")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = %s AND pid <> pg_backend_pid()
    """, (db_name,))
    cur.close()
    conn.close()


# ========================================================================
#  ANÁLISE ESTRUTURAL (Pré‑Mesclagem)
# ========================================================================

EXCLUDED_TABLES = frozenset([
    'spatial_ref_sys', 'layer_styles', 'topology', 'raster_columns',
    'raster_overviews', 'geography_columns', 'geometry_columns',
])


def analyze_database(params, db_name):
    """
    Analisa um banco e retorna dict com informações estruturais.
    Retorna:
        {
            "db":        str,
            "schemas":   [str],
            "geo_count": int,
            "tables":    {(schema, table): [col_info, ...]},
            "status":    "compatible" | "no_geo" | "error",
            "obs":       str
        }
    col_info = {"name": str, "type": str, "is_serial": bool}
    """
    result = {"db": db_name, "schemas": [], "geo_count": 0,
              "tables": {}, "status": "error", "obs": ""}
    try:
        conn = get_db_connection(params, db_name)
        cur = conn.cursor()

        # Schemas
        cur.execute("""
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog','information_schema')
              AND schema_name NOT LIKE 'pg_toast%%'
        """)
        result["schemas"] = [r[0] for r in cur.fetchall()]

        # Tabelas espaciais
        cur.execute("""
            SELECT DISTINCT f_table_schema, f_table_name
            FROM geometry_columns
        """)
        geo_tables = cur.fetchall()
        result["geo_count"] = len(geo_tables)

        # Estrutura detalhada das tabelas espaciais + negócio edgv
        cur.execute("""
            SELECT DISTINCT f_table_schema, f_table_name FROM geometry_columns
            UNION
            SELECT schemaname, tablename FROM pg_tables
            WHERE schemaname = 'edgv'
        """)
        all_tables = cur.fetchall()

        for schema, table in all_tables:
            if table in EXCLUDED_TABLES:
                continue
            cur.execute("""
                SELECT c.column_name, c.data_type,
                       CASE WHEN c.column_default LIKE 'nextval%%'
                                 OR c.is_identity = 'YES' THEN true
                            ELSE false END AS is_serial
                FROM information_schema.columns c
                WHERE c.table_schema = %s AND c.table_name = %s
                ORDER BY c.ordinal_position
            """, (schema, table))
            cols = [{"name": r[0], "type": r[1], "is_serial": r[2]}
                    for r in cur.fetchall()]
            result["tables"][(schema, table)] = cols

        cur.close()
        conn.close()

        if result["geo_count"] == 0:
            result["status"] = "no_geo"
            result["obs"] = "Nenhuma camada espacial encontrada"
        else:
            result["status"] = "compatible"

    except Exception as e:
        result["status"] = "error"
        result["obs"] = str(e)

    return result


def compare_structures(analyses):
    """
    Compara as estruturas de N bancos analisados.
    Retorna lista de observações e flag global de compatibilidade.
    {
        "compatible": bool,
        "details": [{"db": str, "status": str, "obs": str, ...}],
        "warnings": [str]
    }
    """
    warnings = []
    if len(analyses) < 2:
        return {"compatible": False, "details": analyses, "warnings": ["Menos de 2 bancos selecionados."]}

    # Referência = primeiro banco compatível
    ref = None
    for a in analyses:
        if a["status"] == "compatible":
            ref = a
            break

    if not ref:
        return {"compatible": False, "details": analyses, "warnings": ["Nenhum banco com geometria encontrado."]}

    ref_table_keys = set(ref["tables"].keys())

    for a in analyses:
        if a["status"] != "compatible":
            continue
        other_keys = set(a["tables"].keys())

        missing = ref_table_keys - other_keys
        extra = other_keys - ref_table_keys

        if missing:
            names = [f"{s}.{t}" for s, t in list(missing)[:5]]
            a["obs"] = f"Faltam tabelas: {', '.join(names)}"
            a["status"] = "warning"
            warnings.append(f"{a['db']}: tabelas ausentes em relação ao banco de referência.")

        if extra:
            names = [f"{s}.{t}" for s, t in list(extra)[:5]]
            warnings.append(f"{a['db']}: tabelas extras ignoradas: {', '.join(names)}")

        # Comparar colunas das tabelas em comum
        common = ref_table_keys & other_keys
        for key in common:
            ref_cols = [c["name"] for c in ref["tables"][key] if not c["is_serial"]]
            other_cols = [c["name"] for c in a["tables"][key] if not c["is_serial"]]
            if ref_cols != other_cols:
                tbl_name = f"{key[0]}.{key[1]}"
                a_diff = set(ref_cols) - set(other_cols)
                if a_diff:
                    warnings.append(f"{a['db']}/{tbl_name}: colunas faltando: {', '.join(list(a_diff)[:5])}")

    compatible_count = sum(1 for a in analyses if a["status"] in ("compatible", "warning"))
    return {
        "compatible": compatible_count >= 2,
        "details": analyses,
        "warnings": warnings,
    }


# ========================================================================
#  SEQUÊNCIAS
# ========================================================================

def fix_sequences(params, db_name, tables):
    """Ajusta sequências (nextval) de cada tabela para MAX(col)."""
    count = 0
    conn = get_db_connection(params, db_name)
    conn.autocommit = True
    cur = conn.cursor()
    for schema, table in tables:
        try:
            cur.execute("""
                SELECT column_name, column_default
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                  AND column_default LIKE 'nextval%%'
            """, (schema, table))
            res = cur.fetchone()
            if res:
                col_name = res[0]
                cur.execute(
                    sql.SQL("SELECT MAX({}) FROM {}.{}").format(
                        sql.Identifier(col_name),
                        sql.Identifier(schema),
                        sql.Identifier(table),
                    )
                )
                max_id = cur.fetchone()[0]
                if max_id:
                    seq_name = res[1].split("'")[1]
                    cur.execute("SELECT setval(%s, %s)", (seq_name, max_id))
                    count += 1
        except Exception as error:
            QgsMessageLog.logMessage(
                f"Não foi possível ajustar a sequência de "
                f"'{schema}.{table}': {error}",
                "ISTools",
                Qgis.Warning,
            )
            continue
    cur.close()
    conn.close()
    return count


# ========================================================================
#  MESCLAGEM
# ========================================================================

def merge_databases(params, source_dbs, target_db, progress_callback=None):
    """
    Mescla N bancos PostGIS em novo banco.
    Retorna dict com:
        status: "success" | "partial" | "error"
        total_registros: int
        total_sequences: int
        warnings: [str]
        errors: [str]
        detail: [(table, src_db, count), ...]
    """
    def log(msg, t="info"):
        if progress_callback:
            progress_callback(msg, t)
        QgsMessageLog.logMessage(msg, "ISTools",
            Qgis.Info if t == "info" else Qgis.Success if t == "ok" else Qgis.Critical)

    result = {
        "status": "error",
        "total_registros": 0,
        "total_sequences": 0,
        "warnings": [],
        "errors": [],
        "detail": [],
    }

    try:
        # 1. Criar banco destino clonando estrutura do primeiro
        log(f"Criando banco de destino '{target_db}'...")
        terminate_db_sessions(params, source_dbs[0])

        conn_admin = get_db_connection(params, "postgres")
        conn_admin.autocommit = True
        cur_admin = conn_admin.cursor()
        cur_admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                sql.Identifier(target_db),
                sql.Identifier(source_dbs[0]),
            )
        )
        cur_admin.close()
        conn_admin.close()
        log("Estrutura base criada.", "ok")

        # 2. Conectar no alvo e descobrir tabelas
        conn_target = get_db_connection(params, target_db)
        conn_target.autocommit = True
        cur_target = conn_target.cursor()

        cur_target.execute("""
            SELECT DISTINCT f_table_schema, f_table_name FROM geometry_columns
            UNION
            SELECT schemaname, tablename FROM pg_tables
            WHERE schemaname = 'edgv' AND tablename NOT IN %s
        """, (tuple(EXCLUDED_TABLES),))
        tables = cur_target.fetchall()

        if not tables:
            conn_target.close()
            result["errors"].append("Nenhuma tabela para mesclar.")
            return result

        # 3. Limpar dados do clone
        log(f"Limpando dados ({len(tables)} tabelas)...")
        for schema, table in tables:
            cur_target.execute(
                sql.SQL("TRUNCATE TABLE {}.{} RESTART IDENTITY CASCADE").format(
                    sql.Identifier(schema),
                    sql.Identifier(table),
                )
            )

        # 4. Copiar dados de cada banco
        for i, src_name in enumerate(source_dbs):
            log(f"Processando ({i+1}/{len(source_dbs)}): {src_name}...")
            try:
                conn_src = get_db_connection(params, src_name)
                cur_src = conn_src.cursor()
            except Exception as e:
                msg = f"Erro ao conectar em {src_name}: {e}"
                log(msg, "error")
                result["errors"].append(msg)
                continue

            for schema, table in tables:
                try:
                    # Descobrir seriais no destino
                    cur_target.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                          AND (column_default LIKE 'nextval%%' OR is_identity = 'YES')
                    """, (schema, table))
                    serial_cols = {r[0] for r in cur_target.fetchall()}

                    cur_src.execute(
                        sql.SQL("SELECT * FROM {}.{}").format(
                            sql.Identifier(schema),
                            sql.Identifier(table),
                        )
                    )
                    all_cols = [d[0] for d in cur_src.description]
                    rows = cur_src.fetchall()
                    if not rows:
                        continue

                    target_cols = [c for c in all_cols if c not in serial_cols]
                    col_idx = [all_cols.index(c) for c in target_cols]
                    final_rows = [tuple(r[i] for i in col_idx) for r in rows]

                    insert_query = sql.SQL(
                        "INSERT INTO {}.{} ({}) VALUES ({})"
                    ).format(
                        sql.Identifier(schema),
                        sql.Identifier(table),
                        sql.SQL(", ").join(map(sql.Identifier, target_cols)),
                        sql.SQL(", ").join(
                            sql.Placeholder() for _ in target_cols
                        ),
                    )
                    cur_target.executemany(insert_query, final_rows)
                    result["detail"].append((f"{schema}.{table}", src_name, len(rows)))
                except Exception as e:
                    msg = f"Erro em {schema}.{table} ({src_name}): {e}"
                    log(msg, "error")
                    result["warnings"].append(msg)

            cur_src.close()
            conn_src.close()

        # 5. Ajustar sequências
        log("Sincronizando sequências...")
        seq_count = fix_sequences(params, target_db, tables)

        total = sum(r[2] for r in result["detail"])
        conn_target.close()

        result["total_registros"] = total
        result["total_sequences"] = seq_count

        # 6. Determinar estado final
        if result["errors"]:
            result["status"] = "error"
            log(f"Concluído com {len(result['errors'])} erro(s) crítico(s). "
                f"{total} registros inseridos, {seq_count} sequências ajustadas.", "error")
        elif result["warnings"]:
            result["status"] = "partial"
            log(f"Concluído com {len(result['warnings'])} aviso(s). "
                f"{total} registros inseridos, {seq_count} sequências ajustadas.", "ok")
        else:
            result["status"] = "success"
            log(f"Mesclagem finalizada com sucesso. "
                f"{total} registros, {seq_count} sequências.", "ok")

        return result

    except Exception as e:
        log(f"Falha crítica: {e}", "error")
        result["errors"].append(str(e))
        return result
