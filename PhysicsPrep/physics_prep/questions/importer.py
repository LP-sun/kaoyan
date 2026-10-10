from .repository import Repository

def import_questions(repository: Repository, path):
    return repository.import_questions(path)
