
---

JARVIS – Padrão Obrigatório de Pipelines

1. Princípios

1. Pipelines são declarativos


2. Execução é determinística


3. Código não publica


4. CI/CD não contém lógica


5. Cada camada tem responsabilidade única




---

2. Responsabilidades por Camada

CI/CD (Workflow)

DEVE

definir PIPELINE

definir variáveis de ambiente / secrets

executar pipeline_runner

publicar artefatos / releases


NÃO DEVE

executar lógica de build

conter lógica de pipeline



---

Pipeline Runner

DEVE

ler PIPELINE

carregar pipeline YAML

resolver componentes via Nexus

executar em ordem

aplicar strict


NÃO DEVE

conter lógica específica

publicar artefatos



---

Pipeline YAML

DEVE

declarar componentes e ordem

conter apenas configuração estática


NÃO DEVE

conter lógica

acessar secrets

publicar artefatos


Exemplo

components:
  installer_builder:
    id: pyinstaller_builder
    hint_path: infrastructure


---

Componentes / Workers

DEVE

executar UMA tarefa

receber context

produzir resultado determinístico


NÃO DEVE

publicar

decidir fluxo

acessar CI/CD


Contrato mínimo (Python)

class Worker(NexusComponent):
    def configure(self, config): ...
    def can_execute(self, context): ...
    def execute(self, context): ...


---

3. Contexto Compartilhado

Estrutura fixa:

context = {
    "env": {},
    "artifacts": {},
    "metadata": {},
}


---

4. Publicação

❗ Proibido no código

Publicação ocorre exclusivamente no CI/CD.

- uses: actions/upload-artifact@v4
- uses: softprops/action-gh-release@v1


---

5. Estrutura Recomendada

app/
├─ core/nexus.py
├─ infrastructure/
├─ runtime/pipeline_runner.py
pipelines/


---

6. Exemplo Completo

Workflow

env:
  PIPELINE: build_installer
  PIPELINE_STRICT: true

- run: python app/runtime/pipeline_runner.py

Pipeline

components:
  installer_builder:
    id: pyinstaller_builder

Worker

class PyInstallerBuilder(NexusComponent):
    def execute(self, context):
        subprocess.check_call(["python", "build_config.py"])


---

7. Regra Final

> Código executa. CI/CD publica. Pipeline descreve. Runner orquestra.



