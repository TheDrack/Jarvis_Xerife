name: "🧬 JARVIS: Homeostase e Auto-Cura"

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write
  issues: write

jobs:
  homeostasis:
    name: "🧪 Vistoria e Auto-Cura"
    # Evita rodar em commits de sincronização do próprio bot
    if: (github.event_name == 'pull_request') || (github.event_name == 'push' && !contains(github.event.head_commit.message, '[Auto-Evolution]'))
    runs-on: ubuntu-latest

    steps:
      - name: 🛰️ Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: 📦 Setup UV
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: 🔧 Ambiente
        run: |
          uv venv --python 3.13
          uv pip install pytest pytest-json-report requests sqlmodel pydantic groq
          echo "PYTHONPATH=$PYTHONPATH:$(pwd)" >> $GITHUB_ENV

      - name: 🔄 Ciclo de Cura (Até 2 Tentativas)
        id: healing
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
        run: |
          ATTEMPT=1
          SUCCESS=false
          while [ $ATTEMPT -le 2 ]; do
            echo "🧪 Tentativa $ATTEMPT..."
            # Roda testes e gera o relatório para o Mutator
            uv run pytest --json-report --json-report-file=report.json tests/ && SUCCESS=true && break
            
            echo "🔬 Analisando Risco com o Mecânico..."
            # Usa o MetabolismAnalyzer para checar se é DNA crítico
            RISK_OUT=$(uv run python scripts/metabolism_analyzer.py --intent "self-healing" --instruction "Reparo de teste" --context "$(cat report.json | jq -c '.summary')")
            
            if echo "$RISK_OUT" | grep -q '"requires_human": true'; then
              echo "⚠️ Risco Crítico: Intervenção humana exigida."
              echo "REASON=$(echo $RISK_OUT | jq -r '.reason')" >> $GITHUB_ENV
              break
            fi

            echo "🩹 Aplicando Cura Automática..."
            # Chama o seu script específico de cura
            uv run python scripts/self_healing_mutator.py --report "report.json"
            
            git config --global user.name "Jarvis-AutoEvolution"
            git config --global user.email "jarvis@bot.com"
            git add -A
            git commit -m "🤖 [Auto-Cura] Tentativa de correção #$ATTEMPT"
            
            ATTEMPT=$((ATTEMPT+1))
          done
          echo "final_status=$SUCCESS" >> $GITHUB_OUTPUT

      - name: ✅ Auto-Merge (Voz do Dono)
        if: steps.healing.outputs.final_status == 'true' && github.event.pull_request.number != null
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          if [ "${{ github.event.pull_request.user.login }}" = "TheDrack" ]; then
            gh pr merge ${{ github.event.pull_request.number }} --auto --merge
          fi

      - name: 🚨 Escalação
        if: steps.healing.outputs.final_status == 'false'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue create --title "🚨 Falha na Homeostase: @TheDrack" \
            --body "O sistema falhou após 2 tentativas ou detectou risco crítico. **Motivo:** ${{ env.REASON }}"
          exit 1
