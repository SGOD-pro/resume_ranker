from src.config.aws import get_client
s3 = get_client('s3')
res = s3.list_objects_v2(Bucket='resume-ranker-prod-storage', Prefix='jobs/ats_check_job/resumes/')
for obj in res.get('Contents', []):
    print(obj['Key'])
