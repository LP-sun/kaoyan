"""Run the local PhysicsPrep study application."""
from pathlib import Path
import os
os.environ.setdefault('GRADIO_ANALYTICS_ENABLED', 'False')
from physics_prep.services.learning import LearningService
from physics_prep.ui.application import build_app


def main():
    from physics_prep.config import Settings
    from physics_prep.llm.client import create_client
    root = Path(__file__).resolve().parent
    settings = Settings.from_env()
    service = LearningService(os.environ.get('PHYSICSPREP_DB_PATH', str(root/'data'/'physics_prep.sqlite3')),root/'data')
    app = build_app(service, lambda:create_client(settings),settings)
    app.queue(default_concurrency_limit=1)
    app.launch(server_name='127.0.0.1',
               server_port=int(os.environ.get('PHYSICSPREP_PORT','7860')),
               share=False,
               inbrowser=os.environ.get('PHYSICSPREP_OPEN_BROWSER','false').lower()=='true')


if __name__ == '__main__':
    main()
