from typing import Dict, List, Union, Any

def normalize_ancestors(ancestors: Union[Dict, List, Any]) -> List[Dict]:
    """Normalize ancestor data into a consistent list format."""
    if isinstance(ancestors, dict):
        # If ancestors_data has ancestor_data field, use that
        if 'ancestor_data' in ancestors and isinstance(ancestors['ancestor_data'], list):
            return ancestors['ancestor_data']
        # If it has the data directly in a dict format
        elif 'id' in ancestors:
            return [{
                'id': ancestors['id'],
                'name': ancestors.get('name', ''),
                'rank': ancestors.get('rank', ''),
                'preferred_common_name': ancestors.get('preferred_common_name', '')
            }]
    elif isinstance(ancestors, list):
        return ancestors
    return [] 