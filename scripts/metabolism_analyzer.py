#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Metabolism Analyzer - Mecânico Revisionador

Este módulo implementa o Mecânico Revisionador do Fluxo de Metabolismo do Jarvis.

Responsabilidades:
1. Interpretar a intenção do evento (correção/criação/modificação/otimização/operacional)
2. Coletar contexto completo (logs, stacktrace, commits, diff, histórico, testes)
3. Classificar o tipo de impacto no DNA (estrutural/comportamental/regressivo/expansivo)
4. Formular explicitamente: motivação, impacto esperado, riscos, hipótese técnica
5. Propor UMA OU MAIS abordagens
6. Selecionar a abordagem MAIS SEGURA, MAIS COERENTE e MAIS ALINHADA ao DNA
7. Decidir se deve ESCALONAR ao COMANDANTE ou prosseguir automaticamente

Critérios de Escalonamento Antecipado:
- Intenção depende de decisão de negócio
- Ambiguidade funcional não resolvível por código
- Falta contexto humano ou externo
- Impacto no DNA é amplo ou irreversível
- Alteração exige julgamento arquitetural humano
"""

import argparse
import asyncio
import datetime
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Any
from enum import Enum

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import AI Gateway for LLM-based intent identification
try:
    # Add app directory to path
    app_path = Path(__file__).parent.parent / "app"
    if str(app_path) not in sys.path:
        sys.path.insert(0, str(app_path))
    
    from adapters.infrastructure.ai_gateway import AIGateway, LLMProvider
    HAS_AI_GATEWAY = True
    logger.info("✅ AI Gateway disponível para identificação de intenção via LLM")
except ImportError as e:
    logger.warning(f"⚠️ AI Gateway não disponível, usando identificação por palavras-chave: {e}")
    HAS_AI_GATEWAY = False
    AIGateway = None
    LLMProvider = None


class IntentType(Enum):
    """Tipos de intenção técnica sobre o DNA"""
    CORRECAO = "correção"           # Corrigir erros e bugs
    CRIACAO = "criação"             # Criar novas funcionalidades
    MODIFICACAO = "modificação"     # Modificar funcionalidades existentes
    OTIMIZACAO = "otimização"       # Otimizar performance/segurança
    OPERACIONAL = "operacional"     # Ações operacionais automatizadas
    VALIDACAO = "validação"         # Validar mudanças propostas (PRs)


class ImpactType(Enum):
    """Tipos de impacto no DNA"""
    ESTRUTURAL = "estrutural"           # Mudanças na arquitetura/estrutura
    COMPORTAMENTAL = "comportamental"   # Mudanças no comportamento
    REGRESSIVO = "regressivo"           # Correções que podem afetar código existente
    EXPANSIVO = "expansivo"             # Adição de novas capacidades


class EscalationReason(Enum):
    """Razões para escalonamento ao COMANDANTE"""
    BUSINESS_DECISION = "Decisão de negócio necessária"
    FUNCTIONAL_AMBIGUITY = "Ambiguidade funcional não resolvível por código"
    MISSING_CONTEXT = "Falta contexto humano ou externo"
    BROAD_IMPACT = "Impacto no DNA é amplo ou irreversível"
    ARCHITECTURAL_JUDGMENT = "Requer julgamento arquitetural humano"
    INSUFFICIENT_INFORMATION = "Informação insuficiente para análise segura"


class MetabolismAnalyzer:
    """
    Mecânico Revisionador - Analisa eventos e determina estratégia metabólica
    """
    
    # Padrões de erro que podem ser auto-corrigidos
    AUTO_FIXABLE_ERRORS = [
        'AssertionError',
        'ImportError',
        'NameError',
        'SyntaxError',
        'TypeError',
        'AttributeError',
        'ValueError',
    ]
    
    # Padrões que requerem intervenção humana
    INFRASTRUCTURE_ERRORS = [
        'Timeout',
        'ConnectionError',
        'HTTPError.*429',
        'HTTPError.*500',
        'HTTPError.*503',
    ]
    
    # Palavras-chave que indicam necessidade de decisão de negócio
    BUSINESS_KEYWORDS = [
        'feature',
        'requirement',
        'business logic',
        'workflow',
        'process',
        'user story',
        'epic',
    ]
    
    # Palavras-chave que indicam mudanças arquiteturais
    ARCHITECTURAL_KEYWORDS = [
        'architecture',
        'refactor',
        'redesign',
        'restructure',
        'framework',
        'pattern',
        'database schema',
        'api contract',
    ]
    
    # Constantes para validação e coleta de contexto
    MIN_CONTEXT_LENGTH = 100  # Mínimo de caracteres de contexto para prosseguir automaticamente
    """
    Threshold mínimo de contexto (100 caracteres) antes de permitir metabolismo automático.
    
    Se o contexto fornecido for menor que este valor, o sistema escalona ao COMANDANTE
    por informação insuficiente. Este valor foi escolhido considerando que uma descrição
    mínima útil deve conter:
    - Tipo do problema (~20 chars)
    - Descrição básica (~50 chars)
    - Contexto mínimo (~30 chars)
    
    Ajuste este valor se necessário, mas valores muito baixos (<50) podem resultar em
    mutações mal informadas, enquanto valores muito altos (>200) podem escalonar
    desnecessariamente.
    """
    MAX_COMMITS_TO_FETCH = 10  # Número de commits recentes para contexto
    GIT_OPERATION_TIMEOUT = 10  # Timeout em segundos para operações git
    
    def __init__(self, repo_path: Optional[str] = None, use_llm: bool = True):
        """
        Inicializa o analisador metabólico
        
        Args:
            repo_path: Caminho do repositório (padrão: diretório atual)
            use_llm: Se True, usa LLM para identificação de intenção; se False, usa palavras-chave
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.use_llm = use_llm and HAS_AI_GATEWAY
        
        # Initialize AI Gateway if available and requested
        self.ai_gateway = None
        if self.use_llm:
            try:
                groq_api_key = os.getenv('GROQ_API_KEY')
                gemini_api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
                
                if groq_api_key or gemini_api_key:
                    self.ai_gateway = AIGateway(
                        groq_api_key=groq_api_key,
                        gemini_api_key=gemini_api_key,
                        default_provider=LLMProvider.GROQ,
                    )
                    logger.info("🤖 Mecânico Revisionador usando LLM para identificação de intenção")
                else:
                    logger.warning("⚠️ Nenhuma API key configurada, usando identificação por palavras-chave")
                    self.use_llm = False
            except Exception as e:
                logger.warning(f"⚠️ Erro ao inicializar AI Gateway, usando palavras-chave: {e}")
                self.use_llm = False
        else:
            logger.info("📝 Mecânico Revisionador usando identificação por palavras-chave")
        
        logger.info(f"🔬 Mecânico Revisionador iniciado - DNA: {self.repo_path}")
    
    def analyze_event(
        self,
        intent: str,
        instruction: str,
        context: str = "",
        event_type: str = ""
    ) -> Dict[str, Any]:
        """
        Analisa um evento e determina a estratégia metabólica
        
        Args:
            intent: Intenção técnica declarada
            instruction: Instrução/descrição detalhada
            context: Contexto adicional
            event_type: Tipo de evento GitHub (issues, PR, etc)
            
        Returns:
            Dicionário com análise completa e decisão
        """
        logger.info("=" * 60)
        logger.info("🔍 INICIANDO ANÁLISE METABÓLICA")
        logger.info("=" * 60)
        
        # 1. Interpretar intenção
        intent_type = self._classify_intent(intent, instruction)
        logger.info(f"📋 Intenção classificada: {intent_type.value}")
        
        # 2. Coletar contexto completo
        full_context = self._collect_context(instruction, context, event_type)
        logger.info(f"📚 Contexto coletado: {len(full_context)} caracteres")
        
        # 3. Classificar impacto no DNA
        impact_type = self._classify_impact(intent_type, instruction, full_context)
        logger.info(f"🎯 Impacto classificado: {impact_type.value}")
        
        # 4. Formular análise explícita
        analysis = self._formulate_analysis(
            intent_type, impact_type, instruction, full_context
        )
        
        # 5. Propor abordagens
        approaches = self._propose_approaches(intent_type, impact_type, analysis)
        logger.info(f"💡 {len(approaches)} abordagem(ns) proposta(s)")
        
        # 6. Selecionar melhor abordagem
        selected_approach = self._select_best_approach(approaches)
        logger.info(f"✅ Abordagem selecionada: {selected_approach['name']}")
        
        # 7. Decidir se deve escalonar ao COMANDANTE
        escalation = self._check_escalation(
            intent_type, impact_type, analysis, full_context
        )
        
        if escalation['required']:
            logger.warning(f"🚨 ESCALONAMENTO AO COMANDANTE: {escalation['reason']}")
        else:
            logger.info("✅ Prosseguir com metabolismo automático")
        
        # Preparar resultado
        result = {
            'intent_type': intent_type.value,
            'impact_type': impact_type.value,
            'motivation': analysis['motivation'],
            'expected_impact': analysis['expected_impact'],
            'risks': analysis['risks'],
            'technical_hypothesis': analysis['technical_hypothesis'],
            'approaches': approaches,
            'selected_approach': selected_approach,
            'requires_human': escalation['required'],
            'escalation_reason': escalation['reason'] if escalation['required'] else None,
            'mutation_strategy': selected_approach['strategy'] if not escalation['required'] else None,
        }
        
        # Salvar análise em arquivo para auditoria
        self._save_analysis(result)
        
        # Exportar para GitHub Actions outputs
        self._export_to_github_actions(result)
        
        logger.info("=" * 60)
        logger.info("✅ ANÁLISE METABÓLICA CONCLUÍDA")
        logger.info("=" * 60)
        
        return result
    
    def _classify_intent(self, intent: str, instruction: str) -> IntentType:
        """
        Classifica a intenção técnica usando LLM (se disponível) ou palavras-chave
        
        Args:
            intent: Intenção declarada pelo usuário
            instruction: Instrução/descrição detalhada
            
        Returns:
            IntentType classificado
        """
        # Usar LLM se disponível e configurado
        if self.use_llm and self.ai_gateway:
            try:
                # Usar asyncio.run para executar código assíncrono
                return asyncio.run(self._classify_intent_with_llm(intent, instruction))
            except Exception as e:
                logger.warning(f"⚠️ Erro ao classificar intenção com LLM: {e}")
                logger.info("📝 Fallback para classificação por palavras-chave")
        
        # Fallback para classificação por palavras-chave
        return self._classify_intent_with_keywords(intent, instruction)
    
    async def _classify_intent_with_llm(self, intent: str, instruction: str) -> IntentType:
        """
        Classifica a intenção técnica usando LLM
        
        Args:
            intent: Intenção declarada pelo usuário
            instruction: Instrução/descrição detalhada
            
        Returns:
            IntentType classificado pela LLM
        """
        logger.info("🤖 Classificando intenção com LLM...")
        
        # Preparar prompt para LLM
        prompt = f"""Você é um analisador técnico especializado em classificar intenções de mudanças em código.

Analise a seguinte solicitação e classifique a intenção técnica em EXATAMENTE uma das seguintes categorias:
- correção: Corrigir erros, bugs, falhas
- criação: Criar novas funcionalidades, adicionar features
- modificação: Modificar/alterar funcionalidades existentes
- otimização: Otimizar performance, segurança, melhorar qualidade
- operacional: Ações operacionais automatizadas, manutenção
- validação: Validar, revisar, verificar mudanças propostas

**Intenção declarada:** {intent}
**Instrução/Descrição:** {instruction}

Responda APENAS com uma das categorias acima (uma única palavra em português, sem acentos quando possível):
correção, criação, modificação, otimização, operacional ou validação"""

        messages = [
            {"role": "user", "content": prompt}
        ]
        
        try:
            # Gerar resposta com LLM
            response = await self.ai_gateway.generate_completion(messages)
            
            # Extrair resposta
            llm_response = response.get('response', '').strip().lower()
            
            # Remover acentos para correspondência
            llm_response_clean = llm_response.replace('ç', 'c').replace('ã', 'a').replace('ê', 'e')
            
            logger.info(f"🤖 LLM classificou como: {llm_response}")
            
            # Mapear resposta para IntentType
            intent_mapping = {
                'correção': IntentType.CORRECAO,
                'correcao': IntentType.CORRECAO,
                'criação': IntentType.CRIACAO,
                'criacao': IntentType.CRIACAO,
                'modificação': IntentType.MODIFICACAO,
                'modificacao': IntentType.MODIFICACAO,
                'otimização': IntentType.OTIMIZACAO,
                'otimizacao': IntentType.OTIMIZACAO,
                'operacional': IntentType.OPERACIONAL,
                'validação': IntentType.VALIDACAO,
                'validacao': IntentType.VALIDACAO,
            }
            
            # Tentar correspondência direta
            for key, value in intent_mapping.items():
                if key in llm_response_clean or key in llm_response:
                    logger.info(f"✅ Intenção identificada via LLM: {value.value}")
                    return value
            
            # Se não encontrou correspondência, usar fallback
            logger.warning(f"⚠️ LLM retornou classificação não reconhecida: '{llm_response}'")
            logger.info("📝 Usando fallback para palavras-chave")
            return self._classify_intent_with_keywords(intent, instruction)
            
        except Exception as e:
            logger.error(f"❌ Erro ao classificar com LLM: {e}")
            logger.info("📝 Usando fallback para palavras-chave")
            return self._classify_intent_with_keywords(intent, instruction)
    
    def _classify_intent_with_keywords(self, intent: str, instruction: str) -> IntentType:
        """
        Classifica a intenção técnica usando palavras-chave (método legado/fallback)
        
        Args:
            intent: Intenção declarada pelo usuário
            instruction: Instrução/descrição detalhada
            
        Returns:
            IntentType classificado por palavras-chave
        """
        intent_lower = intent.lower()
        instruction_lower = instruction.lower()
        
        # Mapear palavras-chave para tipos de intenção
        if any(kw in intent_lower or kw in instruction_lower for kw in ['fix', 'bug', 'error', 'fail', 'corrigir', 'correção']):
            return IntentType.CORRECAO
        elif any(kw in intent_lower or kw in instruction_lower for kw in ['create', 'add', 'new', 'criar', 'adicionar']):
            return IntentType.CRIACAO
        elif any(kw in intent_lower or kw in instruction_lower for kw in ['modify', 'change', 'update', 'modificar', 'alterar']):
            return IntentType.MODIFICACAO
        elif any(kw in intent_lower or kw in instruction_lower for kw in ['optimize', 'improve', 'performance', 'otimizar', 'melhorar']):
            return IntentType.OTIMIZACAO
        elif any(kw in intent_lower or kw in instruction_lower for kw in ['validate', 'review', 'check', 'validar', 'revisar']):
            return IntentType.VALIDACAO
        else:
            return IntentType.OPERACIONAL
    
    def _collect_context(self, instruction: str, context: str, event_type: str) -> str:
        """Coleta contexto completo do repositório"""
        context_parts = []
        
        # Adicionar instrução e contexto fornecidos
        context_parts.append(f"## Instrução\n{instruction}\n")
        if context:
            context_parts.append(f"## Contexto Adicional\n{context}\n")
        
        # Coletar commits recentes
        try:
            recent_commits = subprocess.run(
                ['git', 'log', '--oneline', f'-{self.MAX_COMMITS_TO_FETCH}'],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=self.GIT_OPERATION_TIMEOUT
            )
            if recent_commits.returncode == 0:
                context_parts.append(f"## Commits Recentes\n{recent_commits.stdout}\n")
        except Exception as e:
            logger.warning(f"Não foi possível coletar commits recentes: {e}")
        
        # Coletar status do repositório
        try:
            git_status = subprocess.run(
                ['git', 'status', '--short'],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=self.GIT_OPERATION_TIMEOUT
            )
            if git_status.returncode == 0 and git_status.stdout.strip():
                context_parts.append(f"## Status do Repositório\n{git_status.stdout}\n")
        except Exception as e:
            logger.warning(f"Não foi possível coletar status: {e}")
        
        return "\n".join(context_parts)
    
    def _classify_impact(
        self, intent_type: IntentType, instruction: str, context: str
    ) -> ImpactType:
        """Classifica o tipo de impacto no DNA"""
        instruction_lower = instruction.lower()
        context_lower = context.lower()
        combined = f"{instruction_lower} {context_lower}"
        
        # Verificar palavras-chave arquiteturais
        if any(kw in combined for kw in self.ARCHITECTURAL_KEYWORDS):
            return ImpactType.ESTRUTURAL
        
        # Correções podem ser regressivas
        if intent_type == IntentType.CORRECAO:
            return ImpactType.REGRESSIVO
        
        # Criações são expansivas
        if intent_type == IntentType.CRIACAO:
            return ImpactType.EXPANSIVO
        
        # Modificações afetam comportamento
        if intent_type in [IntentType.MODIFICACAO, IntentType.OTIMIZACAO]:
            return ImpactType.COMPORTAMENTAL
        
        # Padrão: comportamental
        return ImpactType.COMPORTAMENTAL
    
    def _formulate_analysis(
        self,
        intent_type: IntentType,
        impact_type: ImpactType,
        instruction: str,
        context: str
    ) -> Dict[str, str]:
        """Formula análise explícita da mudança"""
        
        # Motivação
        motivation = f"Evento classificado como {intent_type.value} com impacto {impact_type.value} no DNA."
        
        # Impacto esperado
        expected_impact = self._describe_expected_impact(intent_type, impact_type)
        
        # Riscos associados
        risks = self._identify_risks(intent_type, impact_type, instruction, context)
        
        # Hipótese técnica
        technical_hypothesis = self._formulate_hypothesis(intent_type, impact_type)
        
        return {
            'motivation': motivation,
            'expected_impact': expected_impact,
            'risks': risks,
            'technical_hypothesis': technical_hypothesis,
        }
    
    def _describe_expected_impact(
        self, intent_type: IntentType, impact_type: ImpactType
    ) -> str:
        """Descreve o impacto esperado"""
        impact_descriptions = {
            ImpactType.ESTRUTURAL: "Mudanças na arquitetura ou estrutura do código, afetando múltiplos módulos.",
            ImpactType.COMPORTAMENTAL: "Mudanças no comportamento de funcionalidades existentes.",
            ImpactType.REGRESSIVO: "Correções que podem afetar código dependente ou testes existentes.",
            ImpactType.EXPANSIVO: "Adição de novas capacidades sem afetar funcionalidades existentes.",
        }
        return impact_descriptions.get(impact_type, "Impacto não determinado")
    
    def _identify_risks(
        self,
        intent_type: IntentType,
        impact_type: ImpactType,
        instruction: str,
        context: str
    ) -> str:
        """Identifica riscos associados à mudança"""
        risks = []
        
        # Riscos por tipo de impacto
        if impact_type == ImpactType.ESTRUTURAL:
            risks.append("Risco de quebrar contratos de API existentes")
            risks.append("Risco de incompatibilidade com módulos dependentes")
        
        if impact_type == ImpactType.REGRESSIVO:
            risks.append("Risco de introduzir regressões em funcionalidades existentes")
            risks.append("Testes existentes podem falhar")
        
        # Verificar menções a database/schema
        if 'database' in instruction.lower() or 'schema' in context.lower():
            risks.append("CRÍTICO: Mudanças no schema podem ser irreversíveis")
        
        # Verificar menções a segurança
        if any(kw in f"{instruction} {context}".lower() for kw in ['security', 'auth', 'password', 'token']):
            risks.append("CRÍTICO: Mudanças em segurança requerem revisão cuidadosa")
        
        if not risks:
            risks.append("Riscos mínimos identificados")
        
        return " | ".join(risks)
    
    def _formulate_hypothesis(
        self, intent_type: IntentType, impact_type: ImpactType
    ) -> str:
        """Formula hipótese técnica para a mudança"""
        if intent_type == IntentType.CORRECAO:
            return "Aplicar correção mínima e localizada, validando com testes existentes."
        elif intent_type == IntentType.CRIACAO:
            return "Adicionar nova funcionalidade com testes, sem afetar código existente."
        elif intent_type == IntentType.MODIFICACAO:
            return "Modificar funcionalidade existente, atualizando testes correspondentes."
        elif intent_type == IntentType.OTIMIZACAO:
            return "Otimizar implementação mantendo comportamento e contratos existentes."
        else:
            return "Executar ação operacional com validação de integridade."
    
    def _propose_approaches(
        self,
        intent_type: IntentType,
        impact_type: ImpactType,
        analysis: Dict[str, str]
    ) -> List[Dict[str, str]]:
        """Propõe uma ou mais abordagens"""
        approaches = []
        
        # Abordagem 1: Minimal change (sempre proposta)
        approaches.append({
            'name': 'Mudança Mínima',
            'description': 'Aplicar a menor mudança possível que resolve o problema',
            'strategy': 'minimal_change',
            'safety_score': 9,
        })
        
        # Abordagem 2: Comprehensive fix (para correções)
        if intent_type == IntentType.CORRECAO:
            approaches.append({
                'name': 'Correção Abrangente',
                'description': 'Corrigir o problema e casos relacionados identificados',
                'strategy': 'comprehensive_fix',
                'safety_score': 7,
            })
        
        # Abordagem 3: Incremental addition (para criações)
        if intent_type == IntentType.CRIACAO:
            approaches.append({
                'name': 'Adição Incremental',
                'description': 'Adicionar funcionalidade em etapas incrementais',
                'strategy': 'incremental_addition',
                'safety_score': 8,
            })
        
        return approaches
    
    def _select_best_approach(self, approaches: List[Dict[str, str]]) -> Dict[str, str]:
        """Seleciona a abordagem MAIS SEGURA e MAIS COERENTE"""
        # Ordenar por safety_score (maior = mais seguro)
        sorted_approaches = sorted(approaches, key=lambda x: x['safety_score'], reverse=True)
        return sorted_approaches[0]
    
    def _check_escalation(
        self,
        intent_type: IntentType,
        impact_type: ImpactType,
        analysis: Dict[str, str],
        context: str
    ) -> Dict[str, Any]:
        """Verifica se deve escalonar ao COMANDANTE"""
        
        # Verificar palavras-chave de negócio
        if any(kw in context.lower() for kw in self.BUSINESS_KEYWORDS):
            return {
                'required': True,
                'reason': EscalationReason.BUSINESS_DECISION.value
            }
        
        # Verificar mudanças arquiteturais
        if impact_type == ImpactType.ESTRUTURAL:
            if any(kw in context.lower() for kw in self.ARCHITECTURAL_KEYWORDS):
                return {
                    'required': True,
                    'reason': EscalationReason.ARCHITECTURAL_JUDGMENT.value
                }
        
        # Verificar riscos críticos
        if 'CRÍTICO' in analysis['risks']:
            return {
                'required': True,
                'reason': EscalationReason.BROAD_IMPACT.value
            }
        
        # Verificar erros de infraestrutura
        for error_pattern in self.INFRASTRUCTURE_ERRORS:
            if re.search(error_pattern, context, re.IGNORECASE):
                return {
                    'required': True,
                    'reason': EscalationReason.MISSING_CONTEXT.value + " (Erro de infraestrutura)"
                }
        
        # Verificar contexto insuficiente
        if len(context) < self.MIN_CONTEXT_LENGTH:
            return {
                'required': True,
                'reason': EscalationReason.INSUFFICIENT_INFORMATION.value
            }
        
        # Sem necessidade de escalonamento
        return {
            'required': False,
            'reason': None
        }
    
    def _save_analysis(self, result: Dict[str, Any]):
        """Salva análise para auditoria"""
        try:
            analysis_dir = self.repo_path / ".github" / "metabolism_logs"
            analysis_dir.mkdir(parents=True, exist_ok=True)
            
            # Nome do arquivo com timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"analysis_{timestamp}.json"
            
            filepath = analysis_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📄 Análise salva: {filepath}")
        except Exception as e:
            logger.warning(f"Não foi possível salvar análise: {e}")
    
    def _export_to_github_actions(self, result: Dict[str, Any]):
        """Exporta resultado para GitHub Actions outputs"""
        try:
            # Obter GITHUB_OUTPUT environment variable
            github_output = os.getenv('GITHUB_OUTPUT')
            if not github_output:
                logger.warning("GITHUB_OUTPUT não definido - pulando export")
                return
            
            with open(github_output, 'a') as f:
                f.write(f"requires_human={str(result['requires_human']).lower()}\n")
                f.write(f"intent_type={result['intent_type']}\n")
                f.write(f"impact_type={result['impact_type']}\n")
                f.write(f"mutation_strategy={result.get('mutation_strategy', '')}\n")
                f.write(f"escalation_reason={result.get('escalation_reason', '')}\n")
                f.write(f"event_description={result.get('motivation', '')}\n")
            
            logger.info("✅ Outputs exportados para GitHub Actions")
        except Exception as e:
            logger.warning(f"Não foi possível exportar para GitHub Actions: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Mecânico Revisionador - Análise Metabólica do Jarvis'
    )
    parser.add_argument(
        '--intent',
        required=True,
        help='Intenção técnica declarada'
    )
    parser.add_argument(
        '--instruction',
        required=True,
        help='Instrução/descrição detalhada'
    )
    parser.add_argument(
        '--context',
        default='',
        help='Contexto adicional'
    )
    parser.add_argument(
        '--event-type',
        default='',
        help='Tipo de evento GitHub'
    )
    parser.add_argument(
        '--repo-path',
        default=None,
        help='Caminho do repositório'
    )
    parser.add_argument(
        '--use-llm',
        action='store_true',
        default=True,
        help='Usar LLM para identificação de intenção (padrão: True)'
    )
    parser.add_argument(
        '--no-llm',
        action='store_true',
        help='Desabilitar LLM e usar apenas palavras-chave'
    )
    
    args = parser.parse_args()
    
    # Determinar se deve usar LLM
    use_llm = not args.no_llm if args.no_llm else args.use_llm
    
    # Criar analyzer e executar análise
    analyzer = MetabolismAnalyzer(repo_path=args.repo_path, use_llm=use_llm)
    result = analyzer.analyze_event(
        intent=args.intent,
        instruction=args.instruction,
        context=args.context,
        event_type=args.event_type
    )
    
    # Imprimir resultado
    print("\n" + "=" * 60)
    print("RESULTADO DA ANÁLISE METABÓLICA")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Exit code baseado em escalation
    sys.exit(0 if not result['requires_human'] else 1)


if __name__ == '__main__':
    main()
