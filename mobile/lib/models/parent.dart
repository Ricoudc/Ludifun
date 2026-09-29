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

/// Type d'erreur et nombre de fois (30 derniers jours).
typedef ErrorCount = ({String errorType, String label, int count});

/// Même erreur sur la même notion dans au moins 3 séances.
class RecurringError {
  const RecurringError({
    required this.label,
    required this.errorLabel,
    required this.sessions,
    this.lessonTitle,
  });

  factory RecurringError.fromJson(Json json) => RecurringError(
    label: json['label'] as String,
    lessonTitle: json['lesson_title'] as String?,
    errorLabel: json['error_label'] as String,
    sessions: json['sessions'] as int,
  );

  final String label;
  final String? lessonTitle;
  final String errorLabel;
  final int sessions;
}

class Dashboard {
  const Dashboard({
    this.errorTypes = const [],
    this.recurringErrors = const [],
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
    errorTypes: [
      for (final e in (json['error_types'] as List<dynamic>? ?? const []).cast<Json>())
        (
          errorType: e['error_type'] as String,
          label: e['label'] as String,
          count: e['count'] as int,
        ),
    ],
    recurringErrors: [
      for (final e in json['recurring_errors'] as List<dynamic>? ?? const [])
        RecurringError.fromJson(e as Json),
    ],
  );

  final List<ErrorCount> errorTypes;
  final List<RecurringError> recurringErrors;
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
    this.facts,
    this.levelRates = const [],
    this.independence,
  });

  factory NotionProgress.fromJson(Json json) => NotionProgress(
    id: json['id'] as String,
    label: json['label'] as String,
    importance: json['importance'] as int,
    level: (json['level'] as Json)['value'] as int,
    explanation: json['explanation'] as String,
    facts: json['facts'] as String?,
    levelRates: [
      for (final r in json['level_rates'] as List<dynamic>? ?? const [])
        (name: (r as Json)['name'] as String, rate: (r['rate'] as num?)?.toDouble()),
    ],
    independence: (json['independence'] as num?)?.toDouble(),
  );

  final String id;
  final String label;
  final int importance;
  final int level;

  /// Interprétation du moteur (d'après le score et les niveaux validés).
  final String explanation;

  /// Fait observé, chiffré : « Sur les 8 dernières activités : 4 réussies seul… ».
  final String? facts;

  /// Réussite par niveau de compréhension (null : jamais travaillé à ce niveau).
  final List<({String name, double? rate})> levelRates;

  /// Part des réussites obtenues sans aide.
  final double? independence;
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

/// Une étape du plan de révision avant un contrôle.
class PlanStep {
  const PlanStep({required this.day, required this.focus, required this.label, this.done = false});

  factory PlanStep.fromJson(Json json) => PlanStep(
    day: DateTime.parse(json['day'] as String),
    focus: json['focus'] as String,
    label: json['label'] as String,
    done: json['done'] as bool? ?? false,
  );

  final DateTime day;
  final String focus;
  final String label;
  final bool done;
}

/// Contrôle à venir, saisi par le parent ; le plan est recalculé chaque jour.
class Exam {
  const Exam({
    required this.id,
    required this.title,
    required this.examDate,
    this.lessonIds = const [],
    this.plan = const [],
  });

  factory Exam.fromJson(Json json) => Exam(
    id: json['id'] as String,
    title: json['title'] as String,
    examDate: DateTime.parse(json['exam_date'] as String),
    lessonIds: [for (final id in json['lesson_ids'] as List<dynamic>) id as String],
    plan: [for (final p in json['plan'] as List<dynamic>) PlanStep.fromJson(p as Json)],
  );

  final String id;
  final String title;
  final DateTime examDate;
  final List<String> lessonIds;
  final List<PlanStep> plan;
}

/// Une activité d'une séance, et pourquoi le moteur l'a choisie (CDC §126).
class SessionActivity {
  const SessionActivity({
    required this.position,
    required this.block,
    required this.activity,
    required this.notions,
    required this.helpLevel,
    this.result,
    this.reason,
  });

  factory SessionActivity.fromJson(Json json) => SessionActivity(
    position: json['position'] as int,
    block: json['block'] as String,
    activity: json['activity'] as String,
    notions: [for (final n in json['notions'] as List<dynamic>) n as String],
    helpLevel: json['help_level'] as int? ?? 0,
    result: json['result'] as String?,
    reason: json['reason'] as String?,
  );

  final int position;
  final String block;
  final String activity;
  final List<String> notions;
  final int helpLevel;
  final String? result;
  final String? reason;
}

class SessionDetail {
  const SessionDetail({required this.activities, required this.decisions, this.engineVersion});

  factory SessionDetail.fromJson(Json json) => SessionDetail(
    engineVersion: json['engine_version'] as String?,
    activities: [
      for (final a in json['activities'] as List<dynamic>) SessionActivity.fromJson(a as Json),
    ],
    decisions: [for (final d in json['decisions'] as List<dynamic>) (d as Json)['text'] as String],
  );

  final String? engineVersion;
  final List<SessionActivity> activities;

  /// Remédiations, pauses proposées, défis bonus : en une phrase chacune.
  final List<String> decisions;
}

/// Une question ratée, vue par le parent : question, réponse de l'enfant, bonne réponse.
class Mistake {
  const Mistake({
    required this.answeredAt,
    required this.lessonId,
    required this.activityType,
    required this.notions,
    required this.question,
    required this.given,
    required this.expected,
    required this.partial,
    this.lessonTitle,
    this.subject,
  });

  factory Mistake.fromJson(Json json) => Mistake(
    answeredAt: DateTime.parse(json['answered_at'] as String),
    lessonId: json['lesson_id'] as String,
    lessonTitle: json['lesson_title'] as String?,
    subject: json['subject'] as String?,
    activityType: json['activity_type'] as String,
    notions: [for (final n in json['notions'] as List<dynamic>) n as String],
    question: json['question'] as String,
    given: json['given'] as String,
    expected: json['expected'] as String,
    partial: json['partial'] as bool? ?? false,
  );

  final DateTime answeredAt;
  final String lessonId;
  final String? lessonTitle;
  final String? subject;
  final String activityType;
  final List<String> notions;
  final String question;
  final String given;
  final String expected;
  final bool partial;
}

class MistakesPage {
  const MistakesPage({required this.mistakes, this.nextBefore});

  factory MistakesPage.fromJson(Json json) => MistakesPage(
    mistakes: [for (final m in json['mistakes'] as List<dynamic>) Mistake.fromJson(m as Json)],
    nextBefore: json['next_before'] as String?,
  );

  final List<Mistake> mistakes;

  /// Curseur de la page suivante, `null` à la fin.
  final String? nextBefore;
}

/// Un jeu d'une notion, tel que l'enfant le verra (réponses comprises), pour le parent.
class ContentBlock {
  const ContentBlock({required this.title, required this.lines, this.instruction});

  factory ContentBlock.fromJson(Json json) => ContentBlock(
    title: json['title'] as String,
    lines: [for (final l in json['lines'] as List<dynamic>) l as String],
    instruction: json['instruction'] as String?,
  );

  final String title;
  final List<String> lines;

  /// Consigne du jeu, telle que l'enfant la lit (à sa classe).
  final String? instruction;
}

class NotionContent {
  const NotionContent({
    required this.knowledgeId,
    required this.label,
    required this.statement,
    required this.blocks,
  });

  factory NotionContent.fromJson(Json json) => NotionContent(
    knowledgeId: json['knowledge_id'] as String,
    label: json['label'] as String,
    statement: json['statement'] as String,
    blocks: [for (final b in json['blocks'] as List<dynamic>) ContentBlock.fromJson(b as Json)],
  );

  final String knowledgeId;
  final String label;
  final String statement;
  final List<ContentBlock> blocks;
}

class LessonContent {
  const LessonContent({required this.grade, required this.notions, this.title, this.text});

  factory LessonContent.fromJson(Json json) => LessonContent(
    title: json['title'] as String?,
    grade: json['grade'] as String,
    text: json['text'] as String?,
    notions: [for (final n in json['notions'] as List<dynamic>) NotionContent.fromJson(n as Json)],
  );

  final String? title;
  final String grade;

  /// Texte de la leçon tel que l'IA l'a lu.
  final String? text;
  final List<NotionContent> notions;
}
