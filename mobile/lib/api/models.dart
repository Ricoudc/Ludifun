// Modèles miroirs des réponses de l'API (backend/app/schemas.py).

class Child {
  final int id;
  final String displayName;
  final String grade;

  Child({required this.id, required this.displayName, required this.grade});

  factory Child.fromJson(Map<String, dynamic> j) =>
      Child(id: j['id'], displayName: j['display_name'], grade: j['grade']);
}

class Notion {
  final int id;
  final String label;
  final String kind;
  final String content;
  final String importance;

  Notion.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        label = j['label'],
        kind = j['kind'],
        content = j['content'],
        importance = j['importance'];
}

class Lesson {
  final int id;
  final String subject;
  final String grade;
  final String title;
  final String summary;
  final List<Notion> notions;
  final int questionCount;

  Lesson.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        subject = j['subject'],
        grade = j['grade'],
        title = j['title'],
        summary = j['summary'],
        notions = (j['notions'] as List).map((n) => Notion.fromJson(n)).toList(),
        questionCount = j['question_count'];
}

class LessonSummary {
  final int id;
  final String subject;
  final String title;

  LessonSummary.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        subject = j['subject'],
        title = j['title'];
}

class QuizQuestion {
  final int id;
  final int notionId;
  final String kind;
  final int difficulty;
  final String prompt;
  final List<String> choices;
  final List<String> leftItems;
  final List<String> rightItems;
  final String? back;

  QuizQuestion.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        notionId = j['notion_id'],
        kind = j['kind'],
        difficulty = j['difficulty'],
        prompt = j['prompt'],
        choices = List<String>.from(j['choices']),
        leftItems = List<String>.from(j['left_items']),
        rightItems = List<String>.from(j['right_items']),
        back = j['back'];
}

class RevisionSession {
  final int id;
  final String mode;
  final int? timeLimitS;
  final List<QuizQuestion> questions;

  RevisionSession.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        mode = j['mode'],
        timeLimitS = j['time_limit_s'],
        questions = (j['questions'] as List).map((q) => QuizQuestion.fromJson(q)).toList();
}

class AnswerResult {
  final bool correct;
  final double score;
  final String feedback;
  final String expected;
  final List<String> missingPoints;

  AnswerResult.fromJson(Map<String, dynamic> j)
      : correct = j['correct'],
        score = (j['score'] as num).toDouble(),
        feedback = j['feedback'],
        expected = j['expected'],
        missingPoints = List<String>.from(j['missing_points']);
}

class NotionResult {
  final String label;
  final double successRate;
  final String status; // acquis, a_renforcer, a_revoir
  final String levelLabel;

  NotionResult.fromJson(Map<String, dynamic> j)
      : label = j['label'],
        successRate = (j['success_rate'] as num).toDouble(),
        status = j['status'],
        levelLabel = j['level_label'];
}

class SessionReport {
  final int answered;
  final int correct;
  final double scoreOn10;
  final List<NotionResult> notions;
  final String message;

  SessionReport.fromJson(Map<String, dynamic> j)
      : answered = j['answered'],
        correct = j['correct'],
        scoreOn10 = (j['score_on_10'] as num).toDouble(),
        notions = (j['notions'] as List).map((n) => NotionResult.fromJson(n)).toList(),
        message = j['message'];
}

class NotionProgress {
  final int lessonId;
  final String label;
  final int level;
  final String levelLabel;

  NotionProgress.fromJson(Map<String, dynamic> j)
      : lessonId = j['lesson_id'],
        label = j['label'],
        level = j['level'],
        levelLabel = j['level_label'];
}

class SubjectProgress {
  final String subject;
  final double successRate;

  SubjectProgress.fromJson(Map<String, dynamic> j)
      : subject = j['subject'],
        successRate = (j['success_rate'] as num).toDouble();
}

class ChildProgress {
  final int lessons;
  final double successRate;
  final double minutesLast7Days;
  final List<SubjectProgress> subjects;
  final List<NotionProgress> toStrengthen;
  final List<NotionProgress> dueReviews;

  ChildProgress.fromJson(Map<String, dynamic> j)
      : lessons = j['lessons'],
        successRate = (j['success_rate'] as num).toDouble(),
        minutesLast7Days = (j['minutes_last_7_days'] as num).toDouble(),
        subjects = (j['subjects'] as List).map((s) => SubjectProgress.fromJson(s)).toList(),
        toStrengthen = (j['to_strengthen'] as List).map((n) => NotionProgress.fromJson(n)).toList(),
        dueReviews = (j['due_reviews'] as List).map((n) => NotionProgress.fromJson(n)).toList();
}
