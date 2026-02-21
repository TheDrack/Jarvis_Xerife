
   def execute(context=None):
       if context is None:
           context = {}
       task_importance = context.get('task_importance', 0)
       if task_importance > 5:
           return {'priority': 'high'}
       else:
           return {'priority': 'low'}
   