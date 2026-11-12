import 'account.dart' show Json;

/// Une notion d'une leçon de l'enfant, rangée dans le programme.
class ProgrammeNotion {
  const ProgrammeNotion({required this.label, required this.level, this.lessonTitle});

  factory ProgrammeNotion.fromJson(Json json) => ProgrammeNotion(
    label: json['label'] as String,
    lessonTitle: json['lesson_title'] as String?,
    level: (json['level'] as Json)['value'] as int,
  );

  final String label;
  final String? lessonTitle;

  /// 0 à 5 (`Levels`).
  final int level;
}

enum SubStatus { notSeen, started, mastered }

/// Une sous-compétence du programme : pas encore vue, commencée ou maîtrisée.
class SubCompetence {
  const SubCompetence({
    required this.id,
    required this.title,
    required this.grades,
    required this.status,
    required this.notions,
  });

  factory SubCompetence.fromJson(Json json) => SubCompetence(
    id: json['id'] as String,
    title: json['title'] as String,
    grades: [for (final g in json['grades'] as List<dynamic>) g as String],
    status: switch (json['status']) {
      'mastered' => SubStatus.mastered,
      'started' => SubStatus.started,
      _ => SubStatus.notSeen,
    },
    notions: [
      for (final n in json['notions'] as List<dynamic>) ProgrammeNotion.fromJson(n as Json),
    ],
  );

  final String id;
  final String title;
  final List<String> grades;
  final SubStatus status;
  final List<ProgrammeNotion> notions;
}

class ProgrammeCompetence {
  const ProgrammeCompetence({required this.title, required this.subs});

  factory ProgrammeCompetence.fromJson(Json json) => ProgrammeCompetence(
    title: json['title'] as String,
    subs: [for (final s in json['subs'] as List<dynamic>) SubCompetence.fromJson(s as Json)],
  );

  final String title;
  final List<SubCompetence> subs;
}

class ProgrammeDomain {
  const ProgrammeDomain({required this.title, required this.competences});

  factory ProgrammeDomain.fromJson(Json json) => ProgrammeDomain(
    title: json['title'] as String,
    competences: [
      for (final c in json['competences'] as List<dynamic>) ProgrammeCompetence.fromJson(c as Json),
    ],
  );

  final String title;
  final List<ProgrammeCompetence> competences;
}

class ProgrammeSubject {
  const ProgrammeSubject({
    required this.subject,
    required this.total,
    required this.started,
    required this.mastered,
    required this.domains,
    this.elsewhere = const [],
    this.unplaced = const [],
  });

  factory ProgrammeSubject.fromJson(Json json) => ProgrammeSubject(
    subject: json['subject'] as String,
    total: json['total'] as int,
    started: json['started'] as int,
    mastered: json['mastered'] as int,
    domains: [
      for (final d in json['domains'] as List<dynamic>) ProgrammeDomain.fromJson(d as Json),
    ],
    elsewhere: [
      for (final s in json['elsewhere'] as List<dynamic>? ?? const [])
        SubCompetence.fromJson(s as Json),
    ],
    unplaced: [
      for (final n in json['unplaced'] as List<dynamic>? ?? const [])
        ProgrammeNotion.fromJson(n as Json),
    ],
  );

  final String subject;
  final int total;
  final int started;
  final int mastered;
  final List<ProgrammeDomain> domains;

  /// Notions rangées dans le programme d'une autre classe (leçon revue, ou en avance).
  final List<SubCompetence> elsewhere;

  /// Notions que le référentiel ne range nulle part.
  final List<ProgrammeNotion> unplaced;
}

/// Le programme de la classe de l'enfant (§105), et où en sont ses notions.
class Programme {
  const Programme({
    required this.grade,
    required this.version,
    required this.source,
    required this.subjects,
  });

  factory Programme.fromJson(Json json) => Programme(
    grade: json['grade'] as String,
    version: json['version'] as String,
    source: json['source'] as String,
    subjects: [
      for (final s in json['subjects'] as List<dynamic>) ProgrammeSubject.fromJson(s as Json),
    ],
  );

  final String grade;
  final String version;
  final String source;
  final List<ProgrammeSubject> subjects;
}
