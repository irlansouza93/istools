# -*- coding: utf-8 -*-

"""
Sistema de Tradução Bilíngue para Plugins QGIS
Baseado na implementação bem-sucedida do plugin LFTools
"""

from .dictionary import dic


def translate(string, loc):
    """
    Traduz strings baseado no locale
    
    Args:
        string: (inglês, português) ou string única
        loc: código do idioma (pt, en, es, etc.)
    
    Returns:
        str: String traduzida conforme o locale
    """
    try:
        # Português
        if loc == 'pt':
            if isinstance(string, (tuple, list)) and len(string) >= 2:
                return string[1]
            else:
                return string[0] if isinstance(string, (tuple, list)) else string
        
        # Outros idiomas (espanhol, francês, alemão, etc.)
        elif loc in ['es', 'fr', 'de']:
            text_key = string[0] if isinstance(string, (tuple, list)) else string
            
            if text_key in dic and loc in dic[text_key]:
                return dic[text_key][loc]
            
            # Fallback para português se disponível
            if isinstance(string, (tuple, list)) and len(string) >= 2:
                return string[1]
            
            return text_key
        
        # Inglês (padrão)
        else:
            if isinstance(string, (tuple, list)):
                return string[0]
            else:
                return string
                
    except Exception as e:
        # Log do erro para debug
        print(f"Translation error: {e}")
        # Fallback seguro
        if isinstance(string, (tuple, list)) and len(string) > 0:
            return string[0]
        return str(string)
