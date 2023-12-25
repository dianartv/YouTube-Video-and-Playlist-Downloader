import logging

logger = logging

logger.basicConfig(level=logging.INFO,
                   filename=r"logs\logs.log",
                   filemode="a",
                   format="%(asctime)s %(levelname)s %(message)s",
                   encoding='utf-8')
