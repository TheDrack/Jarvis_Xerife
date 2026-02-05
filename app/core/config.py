# -*- coding: utf-8 -*-
"""
Configuration file for the application.
Contains paths to Excel files and other configuration settings.
"""
import os

# Base directory for the ServicoAutomatico folder
BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'ServicoAutomatico')

# Excel file paths
EXCEL_PATHS = {
    'sites': os.path.join(BASE_DIR, 'Lista de Sites.xlsx'),
    'centro_custo': os.path.join(BASE_DIR, 'Lista de CC.xlsx'),
    'materiais': os.path.join(BASE_DIR, 'Lista de Materiais.xlsx'),
    'inventario': os.path.join(BASE_DIR, 'inventario.xls'),
}

def get_excel_path(key):
    """
    Get the path to an Excel file by key.
    
    Args:
        key: The key identifying the Excel file ('sites', 'centro_custo', 'materiais', 'inventario')
    
    Returns:
        The full path to the Excel file
    """
    return EXCEL_PATHS.get(key)