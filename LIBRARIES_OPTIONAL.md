# HealthReport Studio — Librerie Opzionali
#
# Installa SOLO i driver dei database che usi effettivamente.
# Comando: pip install <nome_pacchetto>
#
# Se vuoi installarli tutti in una volta (non consigliato):
#   pip install -r requirements_optional.txt

## Driver DB on-premise
# psycopg2-binary      → PostgreSQL / Supabase / Neon / Azure PG / Cloud SQL
# pymysql              → MySQL / MariaDB / PlanetScale
# pyodbc               → MSSQL / SQL Server / Azure SQL / Synapse / Access
# oracledb             → Oracle Database
# duckdb               → DuckDB locale
# duckdb-engine        → DuckDB con SQLAlchemy
# fdb                  → Firebird
# ibm_db               → IBM DB2
# ibm_db_sa            → IBM DB2 con SQLAlchemy

## Driver DB cloud — AWS
# redshift-connector   → Amazon Redshift
# sqlalchemy-redshift  → Amazon Redshift con SQLAlchemy
# PyAthena             → Amazon Athena

## Driver DB cloud — Google Cloud
# google-cloud-bigquery  → BigQuery
# sqlalchemy-bigquery    → BigQuery con SQLAlchemy
# pg8000                 → Cloud SQL via connector
# cloud-sql-python-connector → Cloud SQL
# google-cloud-spanner   → Cloud Spanner
# sqlalchemy-spanner     → Cloud Spanner con SQLAlchemy

## Driver DB cloud — Azure
# azure-cosmos         → Azure Cosmos DB

## Driver DB cloud — altri
# snowflake-connector-python → Snowflake
# snowflake-sqlalchemy       → Snowflake con SQLAlchemy
# databricks-sql-connector   → Databricks SQL
# sqlalchemy-databricks      → Databricks con SQLAlchemy
# pymongo                    → MongoDB Atlas
# influxdb-client            → InfluxDB 2.x
# elasticsearch              → Elasticsearch
# eland                      → Elasticsearch → DataFrame
# clickhouse-driver          → ClickHouse
# sqlalchemy-clickhouse      → ClickHouse con SQLAlchemy
# sqlalchemy-cockroachdb     → CockroachDB
# boto3                      → AWS DynamoDB / S3 / Athena SDK

## Export report
# python-pptx          → Esporta grafici in PowerPoint (.pptx)
# python-docx          → Esporta report in Word/ODT

## Profilo scientifico condiviso con requirements CS 4407
# seaborn              → Visualizzazione statistica
# jupyterlab           → Notebook di esplorazione, separati dall'app desktop
# torch                → PyTorch per modelli neurali da sviluppare su dati verificati
# einops               → Trasformazioni di tensori
# pandera              → Verifica dello schema dei flussi visite
# yellowbrick          → Diagnostica di modelli scikit-learn
# optuna               → Ricerca di iperparametri
# shap                 → Interpretazione di modelli predittivi
# tenacity             → Retry per integrazioni esterne future
# lime                 → Spiegazioni locali di modelli
# imbalanced-learn     → Apprendimento su classi sbilanciate
# hypothesis           → Test generativi del workflow
