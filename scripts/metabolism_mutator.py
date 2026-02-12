#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Metabolism Mutator - Mecânico Consertador

Este módulo implementa o Mecânico Consertador do Fluxo de Metabolismo do Jarvis.

Responsabilidades:
1. Implementar a mutação proposta pelo Mecânico Revisionador
2. Atualizar ou criar testes (anticorpos) conforme necessário
3. Respeitar padrões e contratos existentes
4. Evitar mutações desnecessárias
5. Registrar todas as mutações em logs auditáveis

Princípios:
- Nenhuma mutação silenciosa é permitida
- Preservar integridade do DNA
- Aplicar SOMENTE as alterações aprovadas
- Todas as mutações devem ser rastreáveis
"""

import argparse
import datetime
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, List, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MetabolismMutator:
    """
    Mecânico Consertador - Implementa mutagênese controlada no DNA
    """
    
    # Timeouts e constantes de configuração
    COPILOT_TIMEOUT_SECONDS = 60  # Timeout para consultas ao GitHub Copilot
    COPILOT_CHECK_TIMEOUT = 10    # Timeout para verificação de disponibilidade
    
    def __init__(self, repo_path: Optional[str] = None):
        """
        Inicializa o mutador metabólico
        
        Args:
            repo_path: Caminho do repositório (padrão: diretório atual)
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.mutation_log = []
        logger.info(f"🔧 Mecânico Consertador iniciado - DNA: {self.repo_path}")
        
        # Verificar GitHub Copilot CLI
        self._check_copilot_cli()
    
    def _check_copilot_cli(self):
        """Verifica se GitHub Copilot CLI está disponível"""
        try:
            result = subprocess.run(
                ['gh', 'copilot', '--version'],
                capture_output=True,
                text=True,
                timeout=self.COPILOT_CHECK_TIMEOUT
            )
            if result.returncode == 0:
                logger.info("✅ GitHub Copilot CLI disponível")
            else:
                logger.warning("⚠️ GitHub Copilot CLI não disponível - funcionalidade limitada")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao verificar Copilot CLI: {e}")
    
    def apply_mutation(
        self,
        strategy: str,
        intent: str,
        impact: str
    ) -> Dict[str, Any]:
        """
        Aplica mutação controlada no DNA
        
        Args:
            strategy: Estratégia de mutação (minimal_change, comprehensive_fix, etc)
            intent: Tipo de intenção (correção, criação, etc)
            impact: Tipo de impacto (estrutural, comportamental, etc)
            
        Returns:
            Dicionário com resultado da mutação
        """
        logger.info("=" * 60)
        logger.info("🧬 INICIANDO MUTAGÊNESE CONTROLADA")
        logger.info("=" * 60)
        logger.info(f"Estratégia: {strategy}")
        logger.info(f"Intenção: {intent}")
        logger.info(f"Impacto: {impact}")
        
        # Determinar método de mutação baseado na estratégia
        if strategy == 'minimal_change':
            result = self._apply_minimal_change(intent, impact)
        elif strategy == 'comprehensive_fix':
            result = self._apply_comprehensive_fix(intent, impact)
        elif strategy == 'incremental_addition':
            result = self._apply_incremental_addition(intent, impact)
        else:
            logger.error(f"❌ Estratégia desconhecida: {strategy}")
            result = {
                'success': False,
                'error': f'Estratégia desconhecida: {strategy}'
            }
        
        # Salvar log de mutação
        if result.get('success'):
            self._save_mutation_log(strategy, intent, impact, result)
            self._export_to_github_actions(result)
        
        logger.info("=" * 60)
        logger.info("✅ MUTAGÊNESE CONCLUÍDA")
        logger.info("=" * 60)
        
        return result
    
    def _apply_minimal_change(self, intent: str, impact: str) -> Dict[str, Any]:
        """
        Aplica mudança mínima - estratégia mais segura
        """
        logger.info("🎯 Aplicando mudança mínima...")
        
        # Obter informação do evento/issue
        issue_body = os.getenv('ISSUE_BODY', '')
        issue_number = os.getenv('ISSUE_NUMBER', '')
        
        if not issue_body:
            logger.warning("⚠️ ISSUE_BODY não fornecido - usando informações básicas")
            issue_body = f"Intent: {intent}, Impact: {impact}"
        
        try:
            # Usar GitHub Copilot para gerar sugestão de correção
            prompt = f"""Você é o Mecânico Consertador do Jarvis.

Contexto:
- Intenção: {intent}
- Impacto: {impact}
- Descrição: {issue_body[:500]}

Tarefa:
Gere uma mudança MÍNIMA e LOCALIZADA que resolve o problema descrito.
Siga os princípios:
1. Menor mudança possível
2. Preservar contratos existentes
3. Não afetar código não relacionado
4. Adicionar testes se necessário

Formato da resposta:
Arquivo: <caminho do arquivo>
Mudança: <descrição da mudança>
"""
            
            # Executar gh copilot suggest
            logger.info("🤖 Consultando GitHub Copilot...")
            result = subprocess.run(
                ['gh', 'copilot', 'suggest', '-t', 'shell', prompt],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.warning(f"⚠️ Copilot não disponível: {result.stderr}")
                # Fallback: criar marcador indicando que mudança manual é necessária
                return self._create_manual_marker(intent, impact, issue_body)
            
            copilot_suggestion = result.stdout
            logger.info(f"✅ Sugestão recebida: {len(copilot_suggestion)} caracteres")
            
            # Por enquanto, registrar a sugestão mas não aplicar automaticamente
            # para evitar mudanças não validadas
            self.mutation_log.append({
                'type': 'minimal_change',
                'suggestion': copilot_suggestion[:500],
                'status': 'suggestion_generated'
            })
            
            return {
                'success': True,
                'mutation_applied': False,  # Não aplicado automaticamente
                'suggestion': copilot_suggestion,
                'files_changed': [],
                'message': 'Sugestão gerada - aguardando aprovação'
            }
            
        except subprocess.TimeoutExpired:
            logger.error("❌ Timeout ao consultar Copilot")
            return {
                'success': False,
                'error': 'Timeout ao consultar GitHub Copilot'
            }
        except Exception as e:
            logger.error(f"❌ Erro ao aplicar mudança: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _apply_comprehensive_fix(self, intent: str, impact: str) -> Dict[str, Any]:
        """
        Aplica correção abrangente - identifica e corrige casos relacionados
        """
        logger.info("🔍 Aplicando correção abrangente...")
        
        # Similar ao minimal_change mas com escopo mais amplo
        # Por segurança, ainda requer validação humana
        return {
            'success': True,
            'mutation_applied': False,
            'message': 'Correção abrangente requer validação humana'
        }
    
    def _apply_incremental_addition(self, intent: str, impact: str) -> Dict[str, Any]:
        """
        Aplica adição incremental - adiciona funcionalidade em etapas
        """
        logger.info("➕ Aplicando adição incremental...")
        
        # Similar às outras estratégias
        return {
            'success': True,
            'mutation_applied': False,
            'message': 'Adição incremental requer validação humana'
        }
    
    def _create_manual_marker(
        self, intent: str, impact: str, issue_body: str
    ) -> Dict[str, Any]:
        """
        Cria marcador para mudança manual quando automação não está disponível
        """
        logger.info("📝 Criando marcador para mudança manual...")
        
        try:
            # Criar arquivo de marcador
            marker_dir = self.repo_path / ".github" / "metabolism_markers"
            marker_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            marker_file = marker_dir / f"mutation_{timestamp}.md"
            
            marker_content = f"""# Marcador de Mutação Metabólica

**Timestamp:** {timestamp}
**Intenção:** {intent}
**Impacto:** {impact}

## Descrição do Evento

{issue_body}

## Ação Necessária

O Mecânico Consertador identificou que esta mutação requer implementação manual.

### Próximos Passos:

1. Revisar a descrição do evento acima
2. Implementar a mudança necessária
3. Adicionar ou atualizar testes
4. Executar suíte de testes
5. Commit e push das mudanças

### Princípios a Seguir:

- ✅ Mudança mínima e localizada
- ✅ Preservar contratos existentes
- ✅ Adicionar testes (anticorpos)
- ✅ Respeitar padrões do projeto
- ✅ Registrar mutação no commit

---

*Gerado automaticamente pelo Fluxo de Metabolismo do Jarvis*
"""
            
            with open(marker_file, 'w', encoding='utf-8') as f:
                f.write(marker_content)
            
            logger.info(f"✅ Marcador criado: {marker_file}")
            
            # Commit o marcador
            subprocess.run(['git', 'add', str(marker_file)], cwd=self.repo_path)
            subprocess.run(
                ['git', 'commit', '-m', f'🔖 Marcador de mutação: {intent}'],
                cwd=self.repo_path
            )
            
            return {
                'success': True,
                'mutation_applied': True,  # Marcador foi criado
                'files_changed': [str(marker_file)],
                'message': 'Marcador de mutação manual criado'
            }
            
        except Exception as e:
            logger.error(f"❌ Erro ao criar marcador: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _save_mutation_log(
        self,
        strategy: str,
        intent: str,
        impact: str,
        result: Dict[str, Any]
    ):
        """Salva log de mutação para auditoria"""
        try:
            log_dir = self.repo_path / ".github" / "metabolism_logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"mutation_{timestamp}.json"
            
            log_data = {
                'timestamp': timestamp,
                'strategy': strategy,
                'intent': intent,
                'impact': impact,
                'result': result,
                'mutation_log': self.mutation_log
            }
            
            filepath = log_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📄 Log de mutação salvo: {filepath}")
        except Exception as e:
            logger.warning(f"Não foi possível salvar log: {e}")
    
    def _export_to_github_actions(self, result: Dict[str, Any]):
        """Exporta resultado para GitHub Actions outputs"""
        try:
            github_output = os.getenv('GITHUB_OUTPUT')
            if not github_output:
                logger.warning("GITHUB_OUTPUT não definido - pulando export")
                return
            
            with open(github_output, 'a') as f:
                f.write(f"mutation_applied={str(result.get('mutation_applied', False)).lower()}\n")
                
                files_changed = result.get('files_changed', [])
                f.write(f"files_changed={','.join(files_changed)}\n")
            
            logger.info("✅ Outputs exportados para GitHub Actions")
        except Exception as e:
            logger.warning(f"Não foi possível exportar para GitHub Actions: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Mecânico Consertador - Mutagênese Controlada do Jarvis'
    )
    parser.add_argument(
        '--strategy',
        required=True,
        help='Estratégia de mutação (minimal_change, comprehensive_fix, incremental_addition)'
    )
    parser.add_argument(
        '--intent',
        required=True,
        help='Tipo de intenção'
    )
    parser.add_argument(
        '--impact',
        required=True,
        help='Tipo de impacto'
    )
    parser.add_argument(
        '--repo-path',
        default=None,
        help='Caminho do repositório'
    )
    
    args = parser.parse_args()
    
    # Criar mutator e executar mutação
    mutator = MetabolismMutator(repo_path=args.repo_path)
    result = mutator.apply_mutation(
        strategy=args.strategy,
        intent=args.intent,
        impact=args.impact
    )
    
    # Imprimir resultado
    print("\n" + "=" * 60)
    print("RESULTADO DA MUTAGÊNESE")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Exit code baseado em sucesso
    sys.exit(0 if result.get('success') else 1)


if __name__ == '__main__':
    main()
