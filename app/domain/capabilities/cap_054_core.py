
   def execute(context=None):
       from airflow import DAG
       from airflow.operators.python import PythonOperator
       from datetime import datetime, timedelta

       default_args = {
           'owner': 'airflow',
           'depends_on_past': False,
           'email_on_failure': False,
           'email_on_retry': False,
           'retries': 1,
           'retry_delay': timedelta(minutes=5)
       }

       def long_running_task():
           # Simula uma tarefa de longa execução
           import time
           time.sleep(60)  # 1 minuto

       with DAG(
           'cap_054',
           default_args=default_args,
           description='Executa ações de longa execução',
           schedule_interval=timedelta(days=1),
           start_date=datetime(2023, 1, 1),
           catchup=False
       ) as dag:
           long_running_task_operator = PythonOperator(
               task_id='long_running_task',
               python_callable=long_running_task
           )

       return dag
   