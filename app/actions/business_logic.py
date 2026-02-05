# -*- coding: utf-8 -*-
"""
Business logic module for the assistente application.
Contains functions for site management, material coding, requisition handling, etc.
"""
import pandas as pd
import webbrowser as wb
from app.core.config import get_excel_path


# Cache for Excel data to optimize repeated queries
_excel_cache = {}


def _load_excel_with_cache(file_key):
    """
    Load Excel file with caching to optimize performance.
    
    Args:
        file_key: The key identifying the Excel file
    
    Returns:
        DataFrame with the Excel data
    """
    if file_key not in _excel_cache:
        file_path = get_excel_path(file_key)
        _excel_cache[file_key] = pd.read_excel(file_path)
    return _excel_cache[file_key]


def clear_cache():
    """Clear the Excel data cache."""
    _excel_cache.clear()


def abrirsite(comando):
    """
    Open a website based on the command.
    
    Args:
        comando: Voice command containing the site name
    """
    url = escolhersite(comando)
    wb.open(url)


def escolhersite(comando):
    """
    Choose the appropriate site URL based on the command.
    Uses optimized pandas query with caching.
    
    Args:
        comando: Voice command containing the site name
    
    Returns:
        URL of the selected site
    """
    site = comando
    
    # Load data with cache
    planilha_de_site = _load_excel_with_cache('sites')
    
    # Optimize: Use itertuples instead of to_numpy().tolist()
    for row in planilha_de_site.itertuples(index=False):
        site_name = row[0]
        url = str(row[1])
        if site_name in site:
            return url
    
    # If no match found, return None (caller should handle)
    return None


def EscolherCentroDeCusto(centro_custo_input):
    """
    Choose the cost center code based on input.
    Uses optimized pandas query with caching.
    
    Args:
        centro_custo_input: Voice command or text with cost center name
    
    Returns:
        Cost center code as string, or None if not found
    """
    # Load data with cache
    df = _load_excel_with_cache('centro_custo')
    
    # Optimize: Use itertuples for better performance
    for row in df.itertuples(index=False):
        codigo = str(row[0])
        escrito = row[1]
        if escrito in centro_custo_input:
            return codigo
    
    return None


def Cod4rMaterial(material_input):
    """
    Get the material code based on the material name/description.
    Uses optimized pandas query with caching.
    
    Args:
        material_input: Voice command or text with material name
    
    Returns:
        Material code as string with leading zero, or the input if not found
    """
    # Load data with cache
    df = _load_excel_with_cache('materiais')
    
    # Optimize: Use itertuples for better performance
    for row in df.itertuples(index=False):
        codigo = str(row[0])
        material = row[1]
        if material in material_input:
            return '0' + codigo
    
    # Return the input if no match found
    return material_input


def FazerRequisicaoPT1(callback_digitar, callback_aperta, callback_falar, callback_ligar_microfone):
    """
    First part of requisition process.
    
    Args:
        callback_digitar: Function to type text
        callback_aperta: Function to press keys
        callback_falar: Function to speak
        callback_ligar_microfone: Function to activate microphone and get input
    """
    callback_falar('Qual centro de custo será o destinatário?')
    cc_input = callback_ligar_microfone()
    cc = EscolherCentroDeCusto(cc_input)
    
    # Use the code if found, otherwise use the original input
    if cc:
        callback_digitar(cc)
    else:
        callback_digitar(cc_input)
    
    callback_aperta('enter')
    callback_aperta('enter')
    
    # Descritivo
    callback_falar('Diga o descritivo')
    desc = callback_ligar_microfone()
    desc = desc.upper()
    callback_digitar(desc)
    callback_aperta('enter')
    
    # Anotação
    callback_falar('Está aos cuidados de qual solicitante?')
    ac = callback_ligar_microfone()
    ac = ac.upper()
    callback_digitar('A/C ' + ac)
    callback_aperta('enter')


def FazerRequisicaoPT2(callback_digitar, callback_aperta, callback_falar, callback_ligar_microfone):
    """
    Second part of requisition process - material entry.
    
    Args:
        callback_digitar: Function to type text
        callback_aperta: Function to press keys
        callback_falar: Function to speak
        callback_ligar_microfone: Function to activate microphone and get input
    """
    # Get material
    callback_falar('Diga o material')
    material_input = callback_ligar_microfone()
    material_code = Cod4rMaterial(material_input)
    callback_digitar(material_code)
    
    # Get quantity
    callback_falar('Fale a quantidade')
    quantidade = callback_ligar_microfone()
    
    if 'pular' not in quantidade:
        callback_aperta('enter')
    
    callback_digitar(quantidade)


def ConsultarEstoque(material_code, callback_falar):
    """
    Consult stock for a material.
    Uses optimized pandas query.
    
    Args:
        material_code: Material code (already processed)
        callback_falar: Function to speak the result
    
    Returns:
        Quantity in stock, or None if not found
    """
    # Load inventory data with cache
    df = _load_excel_with_cache('inventario')
    
    # Optimize: Use itertuples for better performance
    for row in df.itertuples(index=False):
        codigo = str(row[0]).replace('.', '')
        qntd = row[1]
        if material_code in codigo:
            # Ensure qntd is properly formatted for speech
            qntd_str = str(qntd) if qntd is not None else "0"
            callback_falar(qntd_str)
            return qntd
    
    return None
