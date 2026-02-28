# No método de processamento de comandos:
def process_command(self, user_input: str):
    intent = self.intent_processor.process(user_input)
    results = []
    
    for action in intent.actions:
        # Se o estado for incerto, não encadeamos
        if results and results[-1].get('execution_state') == 'uncertain':
            return {"success": False, "error": "Chain broken: previous action lacks evidence of success."}
            
        res = self.executor.execute(action)
        
        # Validação obrigatória
        if not res.get('success') or res.get('execution_state') == 'uncertain':
            logger.warning(f"Ação {action} executada sem evidência observável.")
            
        results.append(res)
    return results
