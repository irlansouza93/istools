import psycopg2
import os
import sys
from psycopg2 import sql

# ATENÇÃO: ESTE SCRIPT APAGA APENAS OS REGISTROS DAS TABELAS DO BANCO DE DESTINO
# ELE PRESERVA O SCHEMA, OS CAMPOS, AS RESTRIÇÕES E OS DOMÍNIOS.

def reset_banco_destino():
    print("==================================================")
    print(" INICIANDO ZERAMENTO DAS FEICOES DO BANCO DESTINO ")
    print("==================================================")
    
    # Parâmetros de proteção garantem que APENAS o banco-destino seja tocado
    db_name = os.environ.get("ISTOOLS_TARGET_DB", "banco-destino")
    
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=os.environ.get("PGUSER", "postgres"),
            password=os.environ.get("PGPASSWORD", ""),
            host=os.environ.get("PGHOST", "localhost"),
            port=os.environ.get("PGPORT", "5432"),
        )
        conn.autocommit = True  # Para poder rodar o TRUNCATE rapidamente
        cur = conn.cursor()
        
        # Queremos apenas esvaziar a pasta (schema) 'edgv' onde estão as geometrias.
        # NUNCA vamos tocar em 'dominios' para não quebrar as constraints do banco!
        schema_name = "edgv"
        
        # Pega todas as tabelas fisicas relativas ao schema edgv:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s",
            (schema_name,),
        )
        tabelas = [row[0] for row in cur.fetchall()]
        
        if not tabelas:
            print(f"Nenhuma tabela encontrada no schema '{schema_name}'.")
            return
            
        print(f"[*] Encontradas {len(tabelas)} tabelas no schema {schema_name}. Truncando dados...")
        
        # Junta todas as tabelas num comando só para evitar que as chaves estrangeiras bloquem a limpeza
        # O CASCADE diz ao postgres que se uma tabela C depende da tabela A, zere ambas sem gritar.
        tabelas_formatadas = sql.SQL(", ").join(
            sql.SQL("{}.{}").format(
                sql.Identifier(schema_name),
                sql.Identifier(table_name),
            )
            for table_name in tabelas
        )

        query_truncate = sql.SQL("TRUNCATE TABLE {} CASCADE").format(
            tabelas_formatadas
        )
        cur.execute(query_truncate)
        
        print("\n[OK] SUCESSO! Todas as tabelas de destino (banco-destino) foram esvaziadas.")
        print("[OK] As tabelas, restrições e dominios continuam intactos. O Banco está pronto para novo ETL!")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"\n[!] Ocorreu um erro ao tentar zerar o banco: {str(e)}")

if __name__ == "__main__":
    confirm = input("Tem certeza que deseja apagar os dados geográficos de 'banco-destino'? (S/N): ")
    if confirm.lower() == 's':
        reset_banco_destino()
    else:
        print("Operação cancelada.")
