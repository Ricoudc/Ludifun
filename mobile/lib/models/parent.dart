import 'account.dart';
import 'level.dart';

/// Formats de l'API de l'espace parent (§11) : liaison, appareils, tableau de bord, historique.

DateTime? _date(Object? value) => value is String ? DateTime.parse(value) : null;

class LinkCode {
  const LinkCode({required this.code, required this.qr, required this.expiresAt});

  factory LinkCode.fromJson(Json json) => LinkCode(
    code: json['code'] as String,
    qr: json['qr'] as String,
    expiresAt: DateTime.parse(json['expires_at'] as String),
  );

  final String code;

  /// Contenu du QR code (`ludifun://lier/<jeton>`).
  final String qr;
  final DateTime expiresAt;
}

class Device {
  const Device({required this.id, required this.createdAt, this.name, this.lastSeenAt});

  factory Device.fromJson(Json json) => Device(
    id: json['id'] as String,
    name: json['name'] as String?,
    createdAt: DateTime.parse(json['created_at'] as String),
    lastSeenAt: _date(json['last_seen_at']),
  );

  final String id;
  final String? name;
  final DateTime createdAt;
  final DateTime? lastSeenAt;
}

class WeekStats {
  const WeekStats({
    required this.weekStart,
    required this.sessions,
    required this.minutes,
    this.averageScore,
  });

  factory WeekStats.fromJson(Json json) => WeekStats(
    weekStart: DateTime.parse(json['week_start'] as String),
    sessions: json['sessions'] as int,
    minutes: json['minutes'] as int,
    averageScore: (json['average_score'] as num?)?.toDouble(),
  );

  final DateTime weekStart;
  final int sessions;
  final int minutes;
  final double? averageScore;
}

class SubjectStats {
  const SubjectStats({
    required this.subject,
    required this.mastery,
    required this.color,
    required this.notions,
  });

  factory SubjectStats.fromJson(Json json) => SubjectStats(
    subject: json['subject'] as String,
    mastery: json['mastery'] as int,
    color: json['color'] as String,
    notions: json['notions'] as int,
  );

  final String subject;
  final int mastery;

  /// `green`, `orange` ou `red`.
  final String color;
  final int notions;
}

class WeakNotion {
  const WeakNotion({
    required this.label,
    required this.mastery,
    required this.status,
    this.lessonTitle,
    this.subject,
    this.level = 0,
    this.explanation,
  });

  factory WeakNotion.fromJson(Json json) => WeakNotion(
    label: json['label'] as String,
    lessonTitle: json['lesson_title'] as String?,
    subject: json['subject'] as String?,
    mastery: json['mastery'] as int,
    status: json['status'] as String,
    level: json['level'] as int? ?? 0,
    explanation: json['explanation'] as String?,
  );

  final String label;
  final String? lessonTitle;
  final String? subject;
  final int mastery;

  /// `to_review` (niveau 3) ou `not_mastered` (niveaux 1 et 2).
  final String status;
  final int level;

  /// Ce qui manque encore (« Reconnaît la bonne réponse, pas encore la retrouver seul. »).
  final String? explanation;
}

class Dashboard {
  const Dashboard({
    required this.thisWeek,
    required this.lessonsAddedThisWeek,
    required this.activities,
    required this.subjects,
    required this.toStrengthen,
    required this.reviewsDue,
    required this.weeks,
    this.trend,
  });

  factory Dashboard.fromJson(Json json) => Dashboard(
    thisWeek: WeekStats.fromJson(json['this_week'] as Json),
    lessonsAddedThisWeek: json['lessons_added_this_week'] as int,
    activities: (json['activities_this_week'] as Json).cast<String, int>(),
    subjects: [for (final s in json['subjects'] as List<dynamic>) SubjectStats.fromJson(s as Json)],
    toStrengthen: [
      for (final n in json['to_strengthen'] as List<dynamic>) WeakNotion.fromJson(n as Json),
    ],
    reviewsDue: json['reviews_due'] as int,
    weeks: [for (final w in json['weeks'] as List<dynamic>) WeekStats.fromJson(w as Json)],
    trend: json['trend'] as String?,
  );

  final WeekStats thisWeek;
  final int lessonsAddedThisWeek;
  final Map<String, int> activities;
  final List<SubjectStats> subjects;
  final List<WeakNotion> toStrengthen;
  final int reviewsDue;

  /// De la plus ancienne à la semaine en cours.
  final List<WeekStats> weeks;

  /// `up`, `down`, `stable`, ou `null` s'il manque des semaines actives.
  final String? trend;
}

class HistoryEntry {
  const HistoryEntry({
    required this.sessionId,
    required this.kind,
    required this.status,
    required this.startedAt,
    required this.minutes,
    required this.notions,
    this.lessonTitle,
    this.subject,
    this.scoreOn10,
  });

  factory HistoryEntry.fromJson(Json json) => HistoryEntry(
    sessionId: json['session_id'] as String,
    lessonTitle: json['lesson_title'] as String?,
    subject: json['subject'] as String?,
    kind: json['kind'] as String,
    status: json['status'] as String,
    startedAt: DateTime.parse(json['started_at'] as String),
    minutes: json['minutes'] as int,
    scoreOn10: (json['score_on_10'] as num?)?.toDouble(),
    notions: [
      for (final n in json['notions'] as List<dynamic>)
        ((n as Json)['label'] as String, n['status'] as String),
    ],
  );

  final String sessionId;
  final String? lessonTitle;
  final String? subject;

  /// `first`, `review` ou `errors`.
  final String kind;

  /// `active`, `completed` ou `abandoned`.
  final String status;
  final DateTime startedAt;
  final int minutes;
  final double? scoreOn10;

  /// (notion, `mastered` | `to_review` | `not_mastered`).
  final List<(String, String)> notions;
}

class HistoryPage {
  const HistoryPage({required this.sessions, this.nextBefore});

  factory HistoryPage.fromJson(Json json) => HistoryPage(
    sessions: [for (final s in json['sessions'] as List<dynamic>) HistoryEntry.fromJson(s as Json)],
    nextBefore: json['next_before'] as String?,
  );

  final List<HistoryEntry> sessions;

  /// Curseur de la page suivante, `null` à la fin.
  final String? nextBefore;
}

/// Une notion et son niveau, dans l'écran « Compétences ».
class NotionProgress {
  const NotionProgress({
    required this.id,
    required this.label,
    required this.importance,
    required this.level,
    required this.explanation,
  });

  factory NotionProgress.fromJson(Json json) => NotionProgress(
    id: json['id'] as String,
    label: json['label'] as String,
    importance: json['importance'] as int,
    level: (json['level'] as Json)['value'] as int,
    explanation: json['explanation'] as String,
  );

  final String id;
  final String label;
  final int importance;
  final int level;
  final String explanation;
}

/// Compétences et notions d'une leçon, avec leur niveau.
class LessonProgress {
  const LessonProgress({
    required this.lessonId,
    required this.createdAt,
    required this.skills,
    required this.notions,
    this.title,
    this.subject,
  });

  factory LessonProgress.fromJson(Json json) => LessonProgress(
    lessonId: json['lesson_id'] as String,
    title: json['title'] as String?,
    subject: json['subject'] as String?,
    createdAt: DateTime.parse(json['created_at'] as String),
    skills: [for (final s in json['skills'] as List<dynamic>) Skill.fromJson(s as Json)],
    notions: [for (final n in json['notions'] as List<dynamic>) NotionProgress.fromJson(n as Json)],
  );

  final String lessonId;
  final String? title;
  final String? subject;
  final DateTime createdAt;
  final List<Skill> skills;
  final List<NotionProgress> notions;

  /// Notions qui ne servent à aucune compétence (ou toutes, pour une leçon sans compétences).
  List<NotionProgress> get notionsWithoutSkill {
    final linked = {for (final s in skills) ...s.knowledgeIds};
    return [
      for (final n in notions)
        if (!linked.contains(n.id)) n,
    ];
  }

  List<NotionProgress> notionsOf(Skill skill) => [
    for (final n in notions)
      if (skill.knowledgeIds.contains(n.id)) n,
  ];
}
