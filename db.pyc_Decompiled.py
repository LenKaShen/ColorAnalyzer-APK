# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'scripts\\db.py'
# Bytecode version: 3.12.0rc2 (3531)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, CheckConstraint, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from typing import List, Dict, Optional
import os
Base = declarative_base()
DB_PATH = 'data/app.db'
os.makedirs('data', exist_ok=True)
engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
class Video(Base):
    __tablename__ = 'videos'
    id = Column(Integer, primary_key=True)
    role = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.now)
    __table_args__ = (CheckConstraint('role IN (\'control_min\', \'control_max\', \'sample\')', name='role_check'),)
class VideoInterval(Base):
    __tablename__ = 'video_intervals'
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey('videos.id'), nullable=False)
    start_time = Column(Float, nullable=False)
    duration = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
class ROI(Base):
    __tablename__ = 'rois'
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey('videos.id'), nullable=False)
    frame_type = Column(String, nullable=False)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    image_width = Column(Integer, nullable=False)
    image_height = Column(Integer, nullable=False)
    __table_args__ = (CheckConstraint('frame_type IN (\'start\', \'end\')', name='frame_type_check'),)
class AnalysisResult(Base):
    __tablename__ = 'analysis_results'
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey('videos.id'), nullable=False)
    delta_e_scalar = Column(Float, nullable=False)
    rate = Column(Float, nullable=False)
    duration = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.now)
    notes = Column(Text, nullable=True)
    interpolated_target = Column(Float, nullable=True)
    calibration_target = Column(Float, nullable=True)
class CalibrationPoint(Base):
    __tablename__ = 'calibration_points'
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey('videos.id'), nullable=False)
    rate = Column(Float, nullable=False)
    target_value = Column(Float, nullable=False)
class Job(Base):
    __tablename__ = 'jobs'
    id = Column(Integer, primary_key=True)
    status = Column(String, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    __table_args__ = (CheckConstraint('status IN (\'pending\', \'running\', \'success\', \'failure\')', name='status_check'),)
def get_db_session():
    return SessionLocal()
def init_db() -> None:
    Base.metadata.create_all(bind=engine)
def insert_video(role: str, filename: str, filepath: str) -> int:
    # ***<module>.insert_video: Failure: Different control flow
    session = get_db_session()
    try:
        video = Video(role=role, filename=filename, filepath=filepath)
        session.add(video)
        session.commit()
        return video.id
    finally:
        pass
def get_video(video_id: int) -> Dict:
    session = get_db_session()
    try:
        video = session.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise ValueError(f'Video {video_id} not found')
        else:
            return {'id': video.id, 'role': video.role, 'filename': video.filename, 'filepath': video.filepath, 'uploaded_at': video.uploaded_at}
    finally:
        session.close()
def get_all_videos() -> List[Dict]:
    session = get_db_session()
    try:
        videos = session.query(Video).all()
        return [{'id': video.id, 'role': video.role, 'filename': video.filename, 'filepath': video.filepath, 'uploaded_at': video.uploaded_at} for video in videos]
    finally:
        session.close()
def upsert_video_interval(video_id: int, start_time: float, duration: float) -> None:
    session = get_db_session()
    try:
        interval = session.query(VideoInterval).filter(VideoInterval.video_id == video_id).first()
        end_time = start_time + duration
        if interval:
            interval.start_time = start_time
            interval.duration = duration
            interval.end_time = end_time
        else:
            interval = VideoInterval(video_id=video_id, start_time=start_time, duration=duration, end_time=end_time)
            session.add(interval)
        session.commit()
    finally:
        session.close()
def upsert_roi(video_id: int, frame_type: str, x: int, y: int, width: int, height: int, image_width: int, image_height: int) -> int:
    # ***<module>.upsert_roi: Failure: Compilation Error
    session = get_db_session()
    try:
        roi = session.query(ROI).filter(ROI.video_id == video_id, ROI.frame_type == frame_type).first()
        if roi:
            roi.x = x
            roi.y = y
            roi.width = width
            roi.height = height
            roi.image_width = image_width
            roi.image_height = image_height
        else:
            roi = ROI(video_id=video_id, frame_type=frame_type, x=x, y=y, width=width, height=height, image_width=image_width, image_height=image_height)
            session.add(roi)
        session.commit()
        @roi.id
    finally:
        session.close()
def get_rois_for_video(video_id: int) -> List[Dict]:
    session = get_db_session()
    try:
        rois = session.query(ROI).filter(ROI.video_id == video_id).all()
        return [{'id': roi.id, 'video_id': roi.video_id, 'frame_type': roi.frame_type, 'x': roi.x, 'y': roi.y, 'width': roi.width, 'height': roi.height, 'image_width': roi.image_width, 'image_height': roi.image_height} for roi in rois]
    finally:
        session.close()
def insert_analysis_result(video_id: int, delta_e_scalar: float, rate: float, duration: float, calibration_target: Optional[float]=None, interpolated_target: Optional[float]=None, notes: Optional[str]=None) -> int:
    # ***<module>.insert_analysis_result: Failure: Compilation Error
    session = get_db_session()
    try:
        result = AnalysisResult(video_id=video_id, delta_e_scalar=delta_e_scalar, rate=rate, duration=duration, calibration_target=calibration_target, interpolated_target=interpolated_target, notes=notes)
        session.add(result)
        session.commit()
        @result.id
    finally:
        session.close()
def insert_calibration_point(video_id: int, rate: float, target_value: float) -> int:
    # ***<module>.insert_calibration_point: Failure: Compilation Error
    session = get_db_session()
    try:
        session.query(CalibrationPoint).filter(CalibrationPoint.video_id == video_id).delete()
        point = CalibrationPoint(video_id=video_id, rate=rate, target_value=target_value)
        session.add(point)
        session.commit()
        @point.id
    finally:
        session.close()
def get_calibration_points() -> List[Dict]:
    session = get_db_session()
    try:
        points = session.query(CalibrationPoint).all()
        return [{'id': point.id, 'video_id': point.video_id, 'rate': point.rate, 'target_value': point.target_value} for point in points]
    finally:
        session.close()
def insert_job(status: str, started_at: Optional[datetime]=None, finished_at: Optional[datetime]=None, error: Optional[str]=None) -> int:
    # ***<module>.insert_job: Failure: Compilation Error
    session = get_db_session()
    try:
        job = Job(status=status, started_at=started_at, finished_at=finished_at, error=error)
        session.add(job)
        session.commit()
        @job.id
    finally:
        session.close()