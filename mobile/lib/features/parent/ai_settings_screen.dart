import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/link_opener.dart';
import '../../core/session.dart';
import '../../models/ai.dart';
import 'goals_screen.dart' show showSnack;

final aiSettingsProvider = FutureProvider.autoDispose<AiSettings>(
  (ref) => ref.watch(apiProvider).aiSettings(),
);

/// « Intelligence artificielle » : l'IA qui lit les photos et crée les jeux, pour toute la
/// famille. Ollama (sur le PC de la maison) est proposé en premier : gratuit, rien ne sort.
class AiSettingsScreen extends ConsumerWidget {
  const AiSettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(
      leading: BackButton(onPressed: () => context.go(Routes.parentHome)),
      title: const Text('Intelligence artificielle'),
    ),
    body: switch (ref.watch(aiSettingsProvider)) {
      AsyncData(:final value) => _AiForm(value),
      AsyncError(:final error) => CenteredBody(
        children: [ErrorMessage(error is ApiException ? error.message : ApiException.unexpected)],
      ),
      _ => const Center(child: CircularProgressIndicator()),
    },
  );
}

class _AiForm extends ConsumerStatefulWidget {
  const _AiForm(this.settings);

  final AiSettings settings;

  @override
  ConsumerState<_AiForm> createState() => _AiFormState();
}

class _AiFormState extends ConsumerState<_AiForm> {
  static const _typingPause = Duration(milliseconds: 900);

  late String _code;
  final _url = TextEditingController();
  final _key = TextEditingController();
  final _model = TextEditingController();
  AiCheck? _check;
  String? _checkedFor; // réglage vérifié par `_check`
  bool _checking = false;
  bool _busy = false;
  int _checkRun = 0; // un résultat arrivé après un autre changement est ignoré
  Timer? _typing;

  AiSettings get _settings => widget.settings;
  AiProvider get _provider => _settings.provider(_code)!;
  FamilyAi? get _saved => _settings.family?.provider == _code ? _settings.family : null;

  @override
  void initState() {
    super.initState();
    final recommended = _settings.providers.firstWhere(
      (p) => p.recommended && p.available,
      orElse: () => _settings.providers.firstWhere((p) => p.available),
    );
    _select(_settings.family?.provider ?? recommended.code);
    WidgetsBinding.instance.addPostFrameCallback((_) => _autoCheck());
  }

  @override
  void dispose() {
    _typing?.cancel();
    _url.dispose();
    _key.dispose();
    _model.dispose();
    super.dispose();
  }

  void _select(String code) {
    _code = code;
    _check = null;
    _checkedFor = null;
    _key.clear();
    _url.text = _saved?.baseUrl ?? _provider.defaultUrl ?? '';
    _model.text = _saved?.model ?? '';
  }

  String? _text(TextEditingController c) => c.text.trim().isEmpty ? null : c.text.trim();

  String get _form => [_code, _url.text.trim(), _model.text.trim(), _key.text.trim()].join('|');

  /// Assez d'informations pour vérifier (sinon on attend la clé, l'adresse ou le modèle).
  bool get _canCheck {
    final p = _provider;
    if (p.code == 'fake') return false;
    if (p.needsKey && _text(_key) == null && _saved?.keyHint == null) return false;
    if (p.customUrl && _text(_url) == null) return false;
    if (p.defaultModel == null && _text(_model) == null) return false;
    return true;
  }

  bool get _checkIsCurrent => _check != null && _checkedFor == _form;

  /// Vérifie l'IA dès qu'on la choisit ou qu'on change un réglage : service joignable, clé
  /// acceptée, modèle présent, et une petite demande d'essai.
  Future<AiCheck?> _runCheck() async {
    _typing?.cancel();
    if (!_canCheck) return null;
    final form = _form;
    final run = ++_checkRun;
    setState(() => _checking = true);
    try {
      final check = await ref
          .read(apiProvider)
          .testAi(_code, model: _text(_model), baseUrl: _text(_url), apiKey: _text(_key));
      if (!mounted || run != _checkRun) return null;
      setState(() {
        _check = check;
        _checkedFor = form;
      });
      return check;
    } on ApiException catch (error) {
      if (!mounted || run != _checkRun) return null;
      final check = AiCheck(ok: false, message: error.message, models: const []);
      setState(() {
        _check = check;
        _checkedFor = form;
      });
      return check;
    } finally {
      if (mounted && run == _checkRun) setState(() => _checking = false);
    }
  }

  void _autoCheck() {
    if (!_checkIsCurrent) unawaited(_runCheck());
  }

  /// Pendant la saisie : on attend une courte pause avant de vérifier.
  void _typed(String _) {
    _typing?.cancel();
    setState(() {});
    _typing = Timer(_typingPause, _autoCheck);
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } on ApiException catch (error) {
      if (mounted) showSnack(context, error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<bool> _confirmBroken(AiCheck check) async =>
      await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Cette IA ne fonctionne pas encore'),
          content: Text(check.message),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Corriger'),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Enregistrer quand même'),
            ),
          ],
        ),
      ) ??
      false;

  Future<void> _save() => _run(() async {
    if (_code != 'fake') {
      final check = _checkIsCurrent ? _check : await _runCheck();
      if (!mounted) return;
      if (check != null && !check.ok && !await _confirmBroken(check)) return;
    }
    await ref
        .read(apiProvider)
        .saveAiSettings(_code, model: _text(_model), baseUrl: _text(_url), apiKey: _text(_key));
    ref.invalidate(aiSettingsProvider);
    if (!mounted) return;
    // La clé est enregistrée (chiffrée) : elle ne reste pas affichée dans le champ.
    final checkedWithKey = _checkIsCurrent;
    _key.clear();
    if (checkedWithKey) _checkedFor = _form;
    showSnack(context, 'IA enregistrée : elle servira dès la prochaine leçon.');
  });

  Future<void> _reset() => _run(() async {
    await ref.read(apiProvider).resetAiSettings();
    ref.invalidate(aiSettingsProvider);
  });

  Widget _status(TextTheme theme) {
    if (_checking) {
      return Row(
        children: [
          const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2)),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              _code == 'ollama'
                  ? 'Vérification de l\'IA… (Ollama peut mettre une minute à charger le modèle)'
                  : 'Vérification de l\'IA…',
            ),
          ),
        ],
      );
    }
    final check = _checkIsCurrent ? _check : null;
    if (check == null) {
      if (_code == 'fake') return const SizedBox.shrink();
      return Text(
        _canCheck
            ? 'Réglage modifié : la vérification va se relancer.'
            : _provider.needsKey
            ? 'Collez la clé : la vérification se lancera toute seule.'
            : 'Indiquez l\'adresse et le modèle : la vérification se lancera toute seule.',
        style: theme.bodyMedium,
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '${check.ok ? '✅' : '⚠️'} ${check.message}',
          style: TextStyle(
            fontSize: 16,
            color: check.ok ? LudiColors.mastered : LudiColors.notMastered,
          ),
        ),
        if (check.models.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('Modèles disponibles (touchez pour choisir) :', style: theme.bodyMedium),
          const SizedBox(height: 4),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final model in check.models.take(30))
                ActionChip(
                  label: Text(model),
                  onPressed: () {
                    setState(() => _model.text = model);
                    _autoCheck();
                  },
                ),
            ],
          ),
        ],
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context).textTheme;
    final family = _settings.family;
    final current = family == null
        ? '${_settings.labelOf(_settings.serverProvider)} (réglage du serveur)'
        : '${_settings.labelOf(family.provider)}${family.model == null ? '' : ' · ${family.model}'}';
    final p = _provider;
    return CenteredBody(
      top: true,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              'IA utilisée en ce moment : $current',
              style: const TextStyle(fontSize: 17),
            ),
          ),
        ),
        const SizedBox(height: 16),
        Text('Quelle IA lit les photos et crée les jeux ?', style: theme.titleMedium),
        const SizedBox(height: 4),
        RadioGroup<String>(
          groupValue: _code,
          onChanged: (code) {
            setState(() => _select(code!));
            _autoCheck();
          },
          child: Column(
            children: [
              for (final provider in _settings.providers)
                if (provider.available)
                  RadioListTile<String>(
                    value: provider.code,
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                      provider.recommended ? '${provider.label} · conseillé' : provider.label,
                      style: TextStyle(
                        fontWeight: provider.recommended ? FontWeight.w700 : FontWeight.w500,
                      ),
                    ),
                    subtitle: provider.code == _code && provider.note.isNotEmpty
                        ? Text(provider.note)
                        : null,
                  ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        if (p.customUrl) ...[
          TextField(
            controller: _url,
            onChanged: _typed,
            keyboardType: TextInputType.url,
            decoration: InputDecoration(
              labelText: p.code == 'ollama' ? 'Adresse d\'Ollama' : 'Adresse de l\'API',
              helperText: p.code == 'ollama'
                  ? 'Laissez l\'adresse proposée si Ollama tourne sur le PC du serveur.'
                  : 'Par exemple https://<ressource>.openai.azure.com/openai/v1',
            ),
          ),
          const SizedBox(height: 12),
        ],
        if (p.asksKey) ...[
          TextField(
            controller: _key,
            onChanged: _typed,
            obscureText: true,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              labelText: p.needsKey ? 'Clé d\'API' : 'Clé d\'API (si le service en demande une)',
              helperText: _saved?.keyHint == null
                  ? null
                  : 'Clé enregistrée ${_saved!.keyHint} : laissez vide pour la garder.',
            ),
          ),
          if (p.keyUrl.isNotEmpty)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: () => ref.read(linkOpenerProvider).open(Uri.parse(p.keyUrl)),
                icon: const Icon(Icons.open_in_new, size: 18),
                label: const Text('Créer une clé'),
              ),
            ),
          const SizedBox(height: 12),
        ] else if (p.code == 'ollama' && p.keyUrl.isNotEmpty)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => ref.read(linkOpenerProvider).open(Uri.parse(p.keyUrl)),
              icon: const Icon(Icons.open_in_new, size: 18),
              label: const Text('Installer Ollama'),
            ),
          ),
        if (p.code != 'fake')
          TextField(
            controller: _model,
            onChanged: _typed,
            autocorrect: false,
            decoration: InputDecoration(
              labelText: p.defaultModel == null ? 'Modèle' : 'Modèle (facultatif)',
              helperText: p.defaultModel == null
                  ? 'Il doit savoir lire les images.'
                  : 'Vide : ${p.defaultModel} (conseillé)',
            ),
          ),
        const SizedBox(height: 16),
        _status(theme),
        const SizedBox(height: 20),
        if (p.code != 'fake')
          OutlinedButton.icon(
            onPressed: _busy || _checking || !_canCheck ? null : _runCheck,
            icon: const Icon(Icons.refresh),
            label: const Text('Vérifier à nouveau'),
          ),
        const SizedBox(height: 12),
        FilledButton(
          onPressed: _busy || _checking ? null : _save,
          child: const Text('Enregistrer'),
        ),
        if (family != null) ...[
          const SizedBox(height: 12),
          TextButton(
            onPressed: _busy ? null : _reset,
            child: const Text('Revenir à l\'IA du serveur'),
          ),
        ],
      ],
    );
  }
}
