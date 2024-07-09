# import global_values
# import re
# import global_values
# import logging
# from thefuzz import fuzz
# from VulnListClass import VulnList

class Component:
    def __init__(self, name, version, data):
        self.name = name
        self.version = version
        self.data = data

    def get_matchtypes(self):
        try:
            return self.data['matchTypes']
        except KeyError:
            return []

    def is_dependency(self):
        dep_types = ['FILE_DEPENDENCY_DIRECT', 'FILE_DEPENDENCY_TRANSITIVE']
        match_types = self.get_matchtypes()
        for m in dep_types:
            if m in match_types:
                return True
        return False

    def is_signature(self):
        sig_types = ['FILE_EXACT', 'FILE_SOME_FILES_MODIFIED', 'FILE_FILES_ADDED_DELETED_AND_MODIFIED',
                     'FILE_EXACT_FILE_MATCH']
        match_types = self.get_matchtypes()
        for m in sig_types:
            if m in match_types:
                return True
        return False

    def is_ignored(self):
        try:
            return self.data['ignored']
        except KeyError:
            return False
