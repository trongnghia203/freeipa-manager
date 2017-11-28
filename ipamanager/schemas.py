"""
GoodData FreeIPA tooling
Configuration parsing tool

Validation schemas for FreeIPA entities configuration.

Kristian Lesko <kristian.lesko@gooddata.com>
"""

from voluptuous import Any, Required

_name_type = Any(str, unicode)
_item_or_list = Any(str, [str])
_schema_memberof = {str: [str]}


schema_settings = {
    'user-group-pattern': str,
    'ignore': {
        Any('user', 'group', 'hostgroup', 'hbacrule', 'sudorule'): [str]
    }
}


schema_users = {
    Required('firstName'): _name_type,
    Required('lastName'): _name_type,
    'initials': str,
    'emailAddress': _item_or_list,
    'organizationUnit': str,
    'manager': str,
    'githubLogin': _item_or_list,
    'title': str,
    'memberOf': _schema_memberof
}


schema_usergroups = {
    'description': str,
    'memberOf': _schema_memberof
}


schema_hostgroups = {
    'description': str,
    'memberOf': _schema_memberof
}


schema_hbac = {
    'description': str,
    'memberHost': [str],
    'memberUser': [str]
}


schema_sudo = {
    'cmdCategory': str,
    'description': str,
    'memberHost': [str],
    'memberUser': [str],
    'options': [str],
    'runAsGroupCategory': str,
    'runAsUserCategory': str
}
