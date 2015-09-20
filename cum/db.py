from cum import output
from cum.config import cum_dir
from natsort import humansorted
from sqlalchemy import (
    Boolean,
    Column,
    create_engine,
    ForeignKey,
    Integer,
    String,
    Table
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.orm.exc import NoResultFound
import sqlalchemy.engine.url
from urllib.parse import urlparse
import click
import os

Base = declarative_base()

group_table = Table(
    'group_association', Base.metadata,
    Column('chapter_id', Integer, ForeignKey('chapters.id')),
    Column('group_id', Integer, ForeignKey('groups.id'))
)


class Series(Base):
    __tablename__ = 'series'

    id = Column(Integer, primary_key=True)

    name = Column(String)
    alias = Column(String, unique=True)
    url = Column(String, unique=True)
    following = Column(Boolean, default=True)

    chapters = relationship("Chapter", backref="series")

    def __init__(self, series):
        self.name = series.name
        self.alias = series.alias
        self.url = series.url

    @property
    def ordered_chapters(self):
        return humansorted(self.chapters, key=lambda x: x.chapter)

    @staticmethod
    def alias_lookup(alias):
        """Returns a DB object for a series by alias name. Prints an error if
        an invalid alias is specified.
        """
        try:
            s = (session.query(Series)
                 .filter_by(alias=alias, following=True)
                 .one())
        except NoResultFound:
            output.error('Could not find alias "{}"'.format(alias))
            exit(1)
        else:
            return s


class Chapter(Base):
    __tablename__ = 'chapters'

    id = Column(Integer, primary_key=True)
    series_id = Column(Integer, ForeignKey('series.id'))

    # Downloaded has the value -1 for ignored chapters, 0 for new chapters and
    # 1 for downloaded chapters.
    downloaded = Column(Integer, default=0)
    chapter = Column(String)
    url = Column(String, unique=True)
    title = Column(String)

    groups = relationship('Group', secondary=group_table, backref='chapters')

    def __init__(self, chapter, series):
        self.series = series
        self.chapter = chapter.chapter
        self.title = chapter.title
        self.url = chapter.url

        self.groups = []
        for group in chapter.groups:
            try:
                g = session.query(Group).filter(Group.name == group).one()
            except NoResultFound:
                g = Group(group)
                session.add(g)
                session.commit()
            self.groups.append(g)

    @property
    def group_tag(self):
        """Return a joined string of chapter's groups enclosed in brackets."""
        return ''.join(['[{}]'.format(x.name) for x in self.groups])

    @property
    def status(self):
        """Return the chapter's downloaded status as a one character flag."""
        if self.downloaded == 0:
            return 'n'
        elif self.downloaded == -1:
            return 'i'
        else:
            return ' '

    @staticmethod
    def find_new(alias=None):
        """Return a list of new chapters as Chapter objects and applies human
        sorting to it. Accepts an optional 'alias' argument, which will filter
        the query.
        """
        query = session.query(Chapter).join(Series).filter(Series.following)
        if alias:
            query = query.filter(Series.alias == alias)
        query = query.filter(Chapter.downloaded == 0).all()
        return humansorted([x.to_object() for x in query],
                           key=lambda x: x.chapter)

    @staticmethod
    def print_new():
        """Prints all new chapters."""
        items = {}
        for chapter in Chapter.find_new():
            try:
                items[chapter.alias].append(chapter.chapter)
            except KeyError:
                items[chapter.alias] = [chapter.chapter]

        for series in sorted(items):
            click.secho(series, bold=True)
            click.echo(click.wrap_text('  '.join([x for x in items[series]]),
                                       width=click.get_terminal_size()[0]))

    def to_object(self):
        """Turns a database entry into a chapter object for the respective
        site by parsing the URL.
        """
        parse = urlparse(self.url)
        kwargs = {'name': self.series.name,
                  'alias': self.series.alias,
                  'chapter': self.chapter,
                  'url': self.url,
                  'groups': self.groups}
        if parse.netloc == 'bato.to':
            from cum.scrapers.batoto import BatotoChapter
            return BatotoChapter(**kwargs)
        elif parse.netloc == 'dynasty-scans.com':
            from cum.scrapers.dynastyscans import DynastyScansChapter
            return DynastyScansChapter(**kwargs)
        elif parse.netloc == 'manga.madokami.com':
            from cum.scrapers.madokami import MadokamiChapter
            return MadokamiChapter(**kwargs)
        else:
            return None


class Group(Base):
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


db_path = os.path.join(cum_dir, 'cum.db')
db_url = sqlalchemy.engine.url.URL('sqlite', database=db_path)
engine = create_engine(db_url)
if not os.path.exists(db_path):
    Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)
session = Session()
