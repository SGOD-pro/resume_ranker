import sys
sys.path.insert(0, '.')
import src.extractors.experience.experience_parser as ep
parser = ep.ExperienceParser()
text = """Dass Systems
Junior Machine Learning Engineer, Jan 2020 - Ongoing
Testing, debugging and parameter tuning for models
developed by the internal team.
B.Tech(IT) from National Institute Of Science And
Technology,Rourkela in 2019
WORK EXPERIENCE
EDUCATION"""
res = parser.parse(text)
print("Entries:", res)
