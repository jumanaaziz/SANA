import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import 'home.dart';
import 'setting.dart';

class ContactPage extends StatefulWidget {
  final bool openAddDialog;

  const ContactPage({
    super.key,
    this.openAddDialog = false,
  });

  @override
  State<ContactPage> createState() => _ContactPageState();
}

class _ContactPageState extends State<ContactPage> {
  @override
void initState() {
  super.initState();

  WidgetsBinding.instance.addPostFrameCallback((_) async {
    await Future.delayed(const Duration(milliseconds: 700));

    if (!mounted) return;
    await _speak('معلومات  الطوارئ');

    if (widget.openAddDialog) {
      await Future.delayed(const Duration(milliseconds: 600));

      if (mounted) {
        _showAddContactDialog();
      }
    }
  });

  }

 
  static const burgundy = Color(0xFF640000);
  static const softBg = Color(0xFFF7F7F8);

  static const int _nameMinLength = 2;
  static const int _nameMaxLength = 40;
  static const int _phoneLength = 10;

  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();
  final FlutterTts _flutterTts = FlutterTts();
  final stt.SpeechToText _speech = stt.SpeechToText();

  bool _speechReady = false;
  bool _isListeningCommand = false;
  bool _isPrimary = false;
  bool _isSaving = false;

  String? get _currentUserId => FirebaseAuth.instance.currentUser?.uid;

  @override
  void dispose() {
    _speech.stop();
    _flutterTts.stop();
    _nameController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  Future<void> _speak(String text) async {
    await _flutterTts.setLanguage('ar-SA');
    await _flutterTts.setSpeechRate(0.45);
    await _flutterTts.setPitch(1.0);
    await _flutterTts.speak(text);
  }

  Future<void> _showPopupAndSpeak({
    required String title,
    required String message,
    IconData icon = Icons.info_outline,
  }) async {
    if (!mounted) return;

    await _speak(message);

    if (!mounted) return;

    showDialog(
      context: context,
      builder: (dialogContext) {
        return Directionality(
          textDirection: TextDirection.rtl,
          child: Dialog(
            backgroundColor: Colors.transparent,
            child: Container(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 18),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(22),
                border: Border.all(color: const Color(0xFFD9D9D9)),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(icon, color: burgundy, size: 54),
                  const SizedBox(height: 14),
                  Text(
                    title,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 30,
                      fontWeight: FontWeight.w900,
                      color: Colors.black,
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    message,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.w700,
                      color: Colors.black,
                      height: 1.35,
                    ),
                  ),
                  const SizedBox(height: 22),
                  SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: ElevatedButton(
                      onPressed: () => Navigator.pop(dialogContext),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: burgundy,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        elevation: 0,
                      ),
                      child: const Text(
                        'حسناً',
                        style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.w900,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  String? _validateContactName(String name) {
    final cleaned = name.trim();

    if (cleaned.isEmpty) return 'الرجاء إدخال اسم جهة الاتصال';
    if (cleaned.length < _nameMinLength) {
      return 'اسم جهة الاتصال يجب أن يكون حرفين على الأقل';
    }
    if (cleaned.length > _nameMaxLength) {
      return 'اسم جهة الاتصال يجب ألا يتجاوز أربعين حرفاً';
    }
    if (!RegExp(r"^[\u0600-\u06FFa-zA-Z\s'-]+$").hasMatch(cleaned)) {
      return 'اسم جهة الاتصال يجب أن يحتوي على حروف فقط';
    }

    return null;
  }

  String? _validateContactPhone(String phone) {
    final cleaned = phone.trim();

    if (cleaned.isEmpty) return 'الرجاء إدخال رقم الجوال';
    if (!RegExp(r'^\d+$').hasMatch(cleaned)) {
      return 'رقم الجوال يجب أن يحتوي على أرقام فقط';
    }
    if (!cleaned.startsWith('05')) return 'رقم الجوال يجب أن يبدأ بـ 05';
    if (cleaned.length != _phoneLength) {
      return 'رقم الجوال يجب أن يتكون من عشرة أرقام';
    }
    if (!RegExp(r'^05\d{8}$').hasMatch(cleaned)) {
      return 'صيغة رقم الجوال غير صحيحة';
    }

    return null;
  }

  Future<bool> _prepareSpeech() async {
    if (!_speechReady) {
      _speechReady = await _speech.initialize();
    }

    if (!_speechReady) {
      await _showPopupAndSpeak(
        title: 'خطأ',
        message: 'تعذر تشغيل الميكروفون',
        icon: Icons.mic_off_outlined,
      );
    }

    return _speechReady;
  }

  Future<String?> _listenArabic({
    Duration maxListenTime = const Duration(seconds: 25),
    Duration silenceTime = const Duration(seconds: 4),
  }) async {
    if (!await _prepareSpeech()) return null;

    String result = '';
    Timer? silenceTimer;
    final completer = Completer<String?>();

    void finish() {
      if (!completer.isCompleted) {
        completer.complete(result.trim().isEmpty ? null : result.trim());
      }
    }

    await _speech.stop();

    await _speech.listen(
      localeId: 'ar_SA',
      listenFor: maxListenTime,
      pauseFor: silenceTime,
      partialResults: true,
      onResult: (value) {
        result = value.recognizedWords;

        silenceTimer?.cancel();
        silenceTimer = Timer(silenceTime, finish);

        if (value.finalResult) {
          finish();
        }
      },
    );

    final text = await completer.future.timeout(
      maxListenTime,
      onTimeout: () => result.trim().isEmpty ? null : result.trim(),
    );

    silenceTimer?.cancel();
    await _speech.stop();

    return text;
  }

  String _spokenNumberToDigits(String text) {
    var normalized = text
        .replaceAll('٠', '0')
        .replaceAll('١', '1')
        .replaceAll('٢', '2')
        .replaceAll('٣', '3')
        .replaceAll('٤', '4')
        .replaceAll('٥', '5')
        .replaceAll('٦', '6')
        .replaceAll('٧', '7')
        .replaceAll('٨', '8')
        .replaceAll('٩', '9')
        .replaceAll('أ', 'ا')
        .replaceAll('إ', 'ا')
        .replaceAll('آ', 'ا')
        .replaceAll('ه', 'ة')
        .replaceAll(',', ' ')
        .replaceAll('-', ' ');

    final directDigits = RegExp(r'\d+')
        .allMatches(normalized)
        .map((match) => match.group(0)!)
        .join();

    final map = {
      'صفر': '0',
      'زيرو': '0',
      'واحد': '1',
      'واحدة': '1',
      'احد': '1',
      'اثنين': '2',
      'اثنان': '2',
      'اتنين': '2',
      'ثنين': '2',
      'ثلاثة': '3',
      'ثلاث': '3',
      'تلاتة': '3',
      'اربعة': '4',
      'اربع': '4',
      'خمسة': '5',
      'خمس': '5',
      'ستة': '6',
      'ست': '6',
      'سبعة': '7',
      'سبع': '7',
      'ثمانية': '8',
      'ثمان': '8',
      'تمانية': '8',
      'تسعة': '9',
      'تسع': '9',
    };

    final buffer = StringBuffer();

    for (final word in normalized.split(RegExp(r'\s+'))) {
      if (RegExp(r'^\d+$').hasMatch(word)) {
        buffer.write(word);
      } else if (map.containsKey(word)) {
        buffer.write(map[word]);
      }
    }

    var digits = buffer.toString().isNotEmpty ? buffer.toString() : directDigits;

    if (digits.length == 9 && digits.startsWith('5')) {
      digits = '0$digits';
    }

    return digits;
  }

  Future<void> _speakDeleteContactMessage() async {
    await _speak('هل تريدين حذف جهة الاتصال هذه؟');
  }

  Future<void> _saveContact() async {
    final userId = _currentUserId;

    if (userId == null) {
      await _showPopupAndSpeak(
        title: 'خطأ',
        message: 'لا يوجد مستخدم مسجل حالياً',
        icon: Icons.person_off_outlined,
      );
      return;
    }

    final name = _nameController.text.trim();
    final phone = _phoneController.text.trim();

    final nameError = _validateContactName(name);
    if (nameError != null) {
      await _speak(nameError);
      return;
    }

    final phoneError = _validateContactPhone(phone);
    if (phoneError != null) {
      await _speak(phoneError);
      return;
    }

    setState(() => _isSaving = true);

    try {
      final contactsRef = FirebaseFirestore.instance.collection('Contact');
      final batch = FirebaseFirestore.instance.batch();

      if (_isPrimary) {
        final oldPrimary =
            await contactsRef.where('userId', isEqualTo: userId).get();

        for (final doc in oldPrimary.docs) {
          batch.update(doc.reference, {'isPrimary': false});
        }
      }

      batch.set(contactsRef.doc(), {
        'userId': userId,
        'name': name,
        'phoneNumber': phone,
        'isPrimary': _isPrimary,
        'createdAt': FieldValue.serverTimestamp(),
      });

      await batch.commit();

      if (!mounted) return;

      Navigator.pop(context);

      await _showPopupAndSpeak(
        title: 'تم الحفظ',
        message: 'تم حفظ جهة الاتصال بنجاح',
        icon: Icons.check_circle_outline,
      );

      _nameController.clear();
      _phoneController.clear();
      _isPrimary = true;
    } catch (e) {
      await _showPopupAndSpeak(
        title: 'خطأ',
        message: 'حدث خطأ أثناء حفظ جهة الاتصال',
        icon: Icons.error_outline,
      );
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  Future<void> _saveContactFromForm(GlobalKey<FormState> formKey) async {
    final isValid = formKey.currentState?.validate() ?? false;

    if (!isValid) {
      final firstError = _validateContactName(_nameController.text) ??
          _validateContactPhone(_phoneController.text);

      if (firstError != null) {
        await _speak(firstError);
      }

      return;
    }

    await _saveContact();
  }

  Future<void> _listenForContactCommand() async {
    if (_isListeningCommand) return;

    setState(() => _isListeningCommand = true);

    await _speak('قولي الأمر');
    final command = await _listenArabic(
      maxListenTime: const Duration(seconds: 12),
      silenceTime: const Duration(seconds: 3),
    );

    if (!mounted) return;
    setState(() => _isListeningCommand = false);

    final text = command
            ?.replaceAll('سنا', '')
            .replaceAll('سانا', '')
            .replaceAll('أريد', '')
            .replaceAll('اريد', '')
            .replaceAll('ابي', '')
            .replaceAll('أبي', '')
            .trim() ??
        '';

    if (text.isEmpty) {
      await _speak('لم أسمع الأمر');
      return;
    }

    if ((text.contains('اضافة') ||
    text.contains('جديدة') ||
            text.contains('إضافة') ||
            text.contains('ضيف') ||
            text.contains('طوارئ') ||
            text.contains('أضيف') ||
            text.contains('اضيف')) &&
        (text.contains('جهة اتصال') ||
            text.contains('جهة') ||
            text.contains('اتصال'))) {
      await _speak('فتح إضافة جهة اتصال');
      if (mounted) _showAddContactDialog();
      return;
    }

    await _speak('لم أفهم الأمر');
  }

  Future<void> _deleteContact(String docId) async {
    await _speakDeleteContactMessage();

    final confirm = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return Directionality(
          textDirection: TextDirection.rtl,
          child: Dialog(
            backgroundColor: Colors.transparent,
            child: Container(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 18),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(24),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.delete_outline,
                    color: burgundy,
                    size: 42,
                  ),
                  const SizedBox(height: 14),
                  const Text(
                    'هل تريدين حذف\nجهة الاتصال هذه؟',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.w900,
                      color: Colors.black,
                      height: 1.2,
                    ),
                  ),
                  const SizedBox(height: 22),
                  SizedBox(
                    width: double.infinity,
                    height: 62,
                    child: ElevatedButton(
                      onPressed: () => Navigator.pop(dialogContext, true),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: burgundy,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                        elevation: 0,
                      ),
                      child: const Text(
                        'حذف',
                        style: TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.w900,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    height: 62,
                    child: ElevatedButton(
                      onPressed: () => Navigator.pop(dialogContext, false),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Color(0xFFE7EAEE),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                        elevation: 0,
                      ),
                      child: const Text(
                        'إلغاء',
                        style: TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.w900,
                          color: Colors.black,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );

    if (confirm != true) return;

    try {
      await FirebaseFirestore.instance.collection('Contact').doc(docId).delete();

      await _showPopupAndSpeak(
        title: 'تم الحذف',
        message: 'تم حذف جهة الاتصال',
        icon: Icons.check_circle_outline,
      );
    } catch (e) {
      await _showPopupAndSpeak(
        title: 'خطأ',
        message: 'حدث خطأ أثناء الحذف',
        icon: Icons.error_outline,
      );
    }
  }

  Future<void> _setPrimary(String selectedDocId, bool makePrimary) async {
    final userId = _currentUserId;

    if (userId == null) {
      await _showPopupAndSpeak(
        title: 'خطأ',
        message: 'لا يوجد مستخدم مسجل حالياً',
        icon: Icons.person_off_outlined,
      );
      return;
    }

    try {
      final contactsRef = FirebaseFirestore.instance.collection('Contact');

      if (!makePrimary) {
        await contactsRef.doc(selectedDocId).update({
          'isPrimary': false,
        });

        await _showPopupAndSpeak(
          title: 'تم التحديث',
          message: 'تم إلغاء جهة الاتصال الأساسية',
          icon: Icons.check_circle_outline,
        );
        return;
      }

      final snapshot =
          await contactsRef.where('userId', isEqualTo: userId).get();

      final batch = FirebaseFirestore.instance.batch();

      for (final doc in snapshot.docs) {
        batch.update(doc.reference, {
          'isPrimary': doc.id == selectedDocId,
        });
      }

      await batch.commit();

      await _showPopupAndSpeak(
        title: 'تم التحديث',
        message: 'تم تعيين جهة الاتصال الأساسية',
        icon: Icons.check_circle_outline,
      );
    } catch (e) {
      await _showPopupAndSpeak(
        title: 'خطأ',
        message: 'حدث خطأ أثناء التحديث',
        icon: Icons.error_outline,
      );
    }
  }

  void _showAddContactDialog() {
    _nameController.clear();
    _phoneController.clear();
    _isPrimary = true;

    final addContactFormKey = GlobalKey<FormState>();
    final nameFieldKey = GlobalKey<FormFieldState<String>>();
    final phoneFieldKey = GlobalKey<FormFieldState<String>>();

    showDialog(
      context: context,
      barrierDismissible: !_isSaving,
      builder: (dialogContext) {
        return Directionality(
          textDirection: TextDirection.rtl,
          child: StatefulBuilder(
            builder: (context, setDialogState) {
              return Dialog(
                insetPadding: const EdgeInsets.symmetric(horizontal: 20),
                backgroundColor: Colors.transparent,
                child: SingleChildScrollView(
                  padding: EdgeInsets.only(
                    bottom: MediaQuery.of(context).viewInsets.bottom,
                  ),
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(22),
                    ),
                    child: Form(
                      key: addContactFormKey,
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Row(
                            children: [
                              Container(
                                width: 48,
                                height: 48,
                                decoration: BoxDecoration(
                                  color: burgundy.withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(14),
                                ),
                                child: const Icon(
                                  Icons.person_add_alt_1,
                                  color: burgundy,
                                  size: 28,
                                ),
                              ),
                              const SizedBox(width: 12),
                              const Expanded(
                                child: Text(
                                  'جهة اتصال جديدة',
                                  style: TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.w900,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 20),
                          const _RequiredLabel('الاسم'),
                          const SizedBox(height: 8),
                          TextFormField(
                            key: nameFieldKey,
                            controller: _nameController,
                            textAlign: TextAlign.right,
                            textInputAction: TextInputAction.next,
                            maxLength: _nameMaxLength,
                            autovalidateMode:
                                AutovalidateMode.onUserInteraction,
                            onTap: () => _speak('أدخلي اسم جهة الاتصال'),
                            validator: (value) =>
                                _validateContactName(value ?? ''),
                            decoration: _inputDecoration(
                              hint: 'مثال: أمي',
                              icon: Icons.person_outline,
                              micAction: () async {
                                await _speak('قولي اسم جهة الاتصال');

                                final text = await _listenArabic();

                                if (text != null) {
                                  setDialogState(() {
                                    _nameController.text =
                                        text.length > _nameMaxLength
                                            ? text.substring(0, _nameMaxLength)
                                            : text;
                                  });

                                  nameFieldKey.currentState?.validate();
                                }
                              },
                            ).copyWith(counterText: ''),
                          ),
                          const SizedBox(height: 16),
                          const _RequiredLabel('رقم الجوال'),
                          const SizedBox(height: 8),
                          TextFormField(
                            key: phoneFieldKey,
                            controller: _phoneController,
                            keyboardType: TextInputType.phone,
                            textAlign: TextAlign.right,
                            maxLength: _phoneLength,
                            autovalidateMode:
                                AutovalidateMode.onUserInteraction,
                            inputFormatters: [
                              FilteringTextInputFormatter.digitsOnly,
                            ],
                            onTap: () => _speak('أدخلي رقم الجوال'),
                            validator: (value) =>
                                _validateContactPhone(value ?? ''),
                            decoration: _inputDecoration(
                              hint: '05XXXXXXXX',
                              icon: Icons.phone_outlined,
                              micAction: () async {
                                await _speak('قولي رقم الجوال');

                                final text = await _listenArabic();

                                if (text != null) {
                                  final digits = _spokenNumberToDigits(text);

                                  setDialogState(() {
                                    _phoneController.text =
                                        digits.length > _phoneLength
                                            ? digits.substring(0, _phoneLength)
                                            : digits;
                                  });

                                  phoneFieldKey.currentState?.validate();
                                }
                              },
                            ).copyWith(counterText: ''),
                          ),
                          const SizedBox(height: 14),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 8,
                            ),
                            decoration: BoxDecoration(
                              color: softBg,
                              borderRadius: BorderRadius.circular(14),
                            ),
                            child: Row(
                              children: [
                                Switch(
                                  value: _isPrimary,
                                  activeColor: burgundy,
                                  onChanged: _isSaving
                                      ? null
                                      : (value) {
                                          setDialogState(() {
                                            _isPrimary = value;
                                          });
                                        },
                                ),
                                const SizedBox(width: 6),
                                const Expanded(
                                  child: Text(
                                    'تعيين كجهة اتصال أساسية',
                                    style: TextStyle(
                                      fontSize: 17,
                                      fontWeight: FontWeight.w800,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 18),
                          Row(
                            children: [
                              Expanded(
                                child: SizedBox(
                                  height: 54,
                                  child: OutlinedButton(
                                    onPressed: _isSaving
                                        ? null
                                        : () => Navigator.pop(dialogContext),
                                    style: OutlinedButton.styleFrom(
                                      foregroundColor: Colors.black,
                                      side: const BorderSide(
                                        color: Color(0xFFD9D9D9),
                                      ),
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(14),
                                      ),
                                    ),
                                    child: const Text(
                                      'إلغاء',
                                      style: TextStyle(
                                        fontSize: 20,
                                        fontWeight: FontWeight.w900,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: SizedBox(
                                  height: 54,
                                  child: FilledButton(
                                    onPressed: _isSaving
                                        ? null
                                        : () => _saveContactFromForm(
                                              addContactFormKey,
                                            ),
                                    style: FilledButton.styleFrom(
                                      backgroundColor: burgundy,
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(14),
                                      ),
                                    ),
                                    child: _isSaving
                                        ? const SizedBox(
                                            width: 24,
                                            height: 24,
                                            child: CircularProgressIndicator(
                                              strokeWidth: 3,
                                              color: Colors.white,
                                            ),
                                          )
                                        : const Text(
                                            'حفظ',
                                            style: TextStyle(
                                              fontSize: 20,
                                              fontWeight: FontWeight.w900,
                                            ),
                                          ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
        );
      },
    );
  }

  InputDecoration _inputDecoration({
    required String hint,
    required IconData icon,
    Future<void> Function()? micAction,
  }) {
    return InputDecoration(
  hintText: hint,
  prefixIcon: Icon(icon, color: burgundy),
  suffixIcon: micAction == null
      ? null
      : IconButton(
          tooltip: 'إملاء صوتي',
          icon: const Icon(
            Icons.mic_none_outlined,
            color: burgundy,
            size: 30,
          ),
          onPressed: micAction,
        ),
  hintStyle: const TextStyle(
        color: Color(0xFF9A9A9A),
        fontWeight: FontWeight.w700,
      ),
      errorStyle: const TextStyle(
        fontSize: 10,
        fontWeight: FontWeight.w800,
        color: Color(0xFFB00020),
      ),
      filled: true,
      fillColor: const Color(0xFFFAFAFA),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: Color(0xFFD0D0D0)),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: Color(0xFFD0D0D0)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: burgundy, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: Color(0xFFB00020), width: 2),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: Color(0xFFB00020), width: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final userId = _currentUserId;

    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        backgroundColor: Colors.white,
        floatingActionButtonLocation: FloatingActionButtonLocation.startFloat,
        floatingActionButton: Padding(
  padding: const EdgeInsets.only(bottom: 72),
  child: InkWell(
    borderRadius: BorderRadius.circular(999),
    onTap: _listenForContactCommand,
    child: Container(
      width: 72,
      height: 72,
      decoration: BoxDecoration(
        color: Colors.white,
        shape: BoxShape.circle,
        border: Border.all(
          color: Color(0xFF640000),
          width: 2,
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x26000000),
            blurRadius: 8,
            offset: Offset(0, 3),
          ),
        ],
      ),
      child: const Icon(
        Icons.mic_none_outlined,
        color: Color(0xFF640000),
        size: 40,
      ),
    ),
  ),
),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
            child: Column(
              children: [
                const SizedBox(height: 18),
                const Text(
                  'معلومات الطوارئ',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 40,
                    fontWeight: FontWeight.w900,
                    color: Colors.black,
                    height: 1,
                  ),
                ),
                const SizedBox(height: 32),
                SizedBox(
                  width: double.infinity,
                  height: 76,
                  child: FilledButton(
                    onPressed: _showAddContactDialog,
                    style: FilledButton.styleFrom(
                      backgroundColor: burgundy,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: const FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text(
                        'إضافة جهة اتصال جديدة',
                        style: TextStyle(
                          fontSize: 34,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 28),
                Expanded(
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 14),
                    decoration: BoxDecoration(
                      color: softBg,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: const Color(0xFFD0D4DB)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const SizedBox(
  width: double.infinity,
  child: FittedBox(
    fit: BoxFit.scaleDown,
    alignment: Alignment.centerRight,
    child: Text(
      'جهات الاتصال المحفوظة',
      maxLines: 1,
      textAlign: TextAlign.right,
      style: TextStyle(
        fontSize: 34,
        fontWeight: FontWeight.w900,
        color: Colors.black,
        height: 1,
      ),
    ),
  ),
),
                        const SizedBox(height: 18),
                        Expanded(
                          child: userId == null
                              ? const _EmptyState(
                                  icon: Icons.lock_outline,
                                  title: 'لا يوجد مستخدم مسجل حالياً',
                                )
                              : StreamBuilder<QuerySnapshot>(
                                  stream: FirebaseFirestore.instance
                                      .collection('Contact')
                                      .where('userId', isEqualTo: userId)
                                      .snapshots(),
                                  builder: (context, snapshot) {
                                    if (snapshot.hasError) {
                                      return const _EmptyState(
                                        icon: Icons.error_outline,
                                        title: 'حدث خطأ أثناء تحميل البيانات',
                                      );
                                    }

                                    if (snapshot.connectionState ==
                                        ConnectionState.waiting) {
                                      return const Center(
                                        child: CircularProgressIndicator(
                                          color: burgundy,
                                        ),
                                      );
                                    }

                                    final docs = snapshot.data?.docs ?? [];

                                    docs.sort((a, b) {
                                      final aData =
                                          a.data() as Map<String, dynamic>;
                                      final bData =
                                          b.data() as Map<String, dynamic>;

                                      final aPrimary =
                                          aData['isPrimary'] == true ? 0 : 1;
                                      final bPrimary =
                                          bData['isPrimary'] == true ? 0 : 1;

                                      return aPrimary.compareTo(bPrimary);
                                    });

                                    if (docs.isEmpty) {
                                      return const _EmptyState(
                                        icon: Icons.contact_phone_outlined,
                                        title: 'لا توجد جهة اتصال محفوظة',
                                      );
                                    }

                                    return ListView.separated(
                                      padding: EdgeInsets.zero,
                                      itemCount: docs.length,
                                      separatorBuilder: (_, __) =>
                                          const SizedBox(height: 14),
                                      itemBuilder: (context, index) {
                                        final doc = docs[index];
                                        final data =
                                            doc.data() as Map<String, dynamic>;

                                        return _ContactCard(
                                          name: data['name'] ?? '',
                                          phoneNumber:
                                              data['phoneNumber'] ?? '',
                                          isPrimary:
                                              data['isPrimary'] == true,
                                          onDelete: () =>
                                              _deleteContact(doc.id),
                                          onSetPrimary: (value) =>
                                              _setPrimary(doc.id, value),
                                        );
                                      },
                                    );
                                  },
                                ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                const _BottomNav(),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RequiredLabel extends StatelessWidget {
  final String text;

  const _RequiredLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: RichText(
        textAlign: TextAlign.right,
        text: TextSpan(
          children: [
            TextSpan(
              text: text,
              style: const TextStyle(
                fontSize: 19,
                fontWeight: FontWeight.w900,
                color: Colors.black,
              ),
            ),
            const TextSpan(
              text: ' *',
              style: TextStyle(
                fontSize: 19,
                fontWeight: FontWeight.w900,
                color: Color(0xFF640000),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
class _ContactCard extends StatelessWidget {
  final String name;
  final String phoneNumber;
  final bool isPrimary;
  final VoidCallback onDelete;
  final ValueChanged<bool> onSetPrimary;

  const _ContactCard({
    required this.name,
    required this.phoneNumber,
    required this.isPrimary,
    required this.onDelete,
    required this.onSetPrimary,
  });

  @override
  Widget build(BuildContext context) {
    const burgundy = ContactPageStateColor.burgundy;

    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFE0E3E8)),
          ),
          child: Row(
            children: [
              Container(
                width: 58,
                height: 58,
                decoration: BoxDecoration(
                  color: burgundy,
                  borderRadius: BorderRadius.circular(9),
                ),
                child: IconButton(
                  onPressed: onDelete,
                  icon: const Icon(
                    Icons.delete_outline,
                    color: Colors.white,
                    size: 38,
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      name,
                      textAlign: TextAlign.right,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 30,
                        fontWeight: FontWeight.w900,
                        color: Colors.black,
                        height: 1,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      phoneNumber,
                      textDirection: TextDirection.ltr,
                      textAlign: TextAlign.right,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w500,
                        color: Color(0xFF596273),
                        height: 1,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 14),
              const Icon(
                Icons.phone_outlined,
                color: burgundy,
                size: 50,
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        const Divider(
          height: 1,
          thickness: 1.5,
          color: Color(0xFFD7DAE0),
        ),
        const SizedBox(height: 18),
        InkWell(
          onTap: () => onSetPrimary(!isPrimary),
          borderRadius: BorderRadius.circular(30),
          child: Row(
            children: [
              Switch(
                value: isPrimary,
                activeColor: burgundy,
                onChanged: onSetPrimary,
              ),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'جهة اتصال أساسية',
                  textAlign: TextAlign.right,
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w900,
                    color: Colors.black,
                    height: 1,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;

  const _EmptyState({
    required this.icon,
    required this.title,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 54,
            color: const Color(0xFF9A9A9A),
          ),
          const SizedBox(height: 12),
          Text(
            title,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 21,
              fontWeight: FontWeight.w800,
              color: Color(0xFF555555),
            ),
          ),
        ],
      ),
    );
  }
}

class ContactPageStateColor {
  static const burgundy = Color(0xFF640000);
}

class _BottomNav extends StatelessWidget {
  const _BottomNav();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 72,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0xFFD9D9D9)),
      ),
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: Row(
          children: [
            Expanded(
              child: NavItem(
                icon: Icons.call_outlined,
                selected: true,
                onTap: () {},
              ),
            ),
            Expanded(
              child: NavItem(
                icon: Icons.settings_outlined,
                selected: false,
                onTap: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const SettingPage()),
                  );
                },
              ),
            ),
            Expanded(
              child: NavItem(
                icon: Icons.home_outlined,
                selected: false,
                onTap: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const HomePage()),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class NavItem extends StatelessWidget {
  final IconData icon;
  final bool selected;
  final VoidCallback? onTap;

  const NavItem({
    super.key,
    required this.icon,
    required this.selected,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        alignment: Alignment.center,
        child: Icon(
          icon,
          size: 50,
          color: selected ? const Color(0xFF640000) : Colors.grey,
        ),
      ),
    );
  }
}
