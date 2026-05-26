import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import 'home.dart';

class SignupPage extends StatefulWidget {
  const SignupPage({super.key});

  @override
  State<SignupPage> createState() => _SignupPageState();
}

class _SignupPageState extends State<SignupPage> {
  static const burgundy = Color(0xFF640000);

  final _formKey = GlobalKey<FormState>();

  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _phoneController = TextEditingController();

  final FlutterTts _flutterTts = FlutterTts();
  final stt.SpeechToText _speech = stt.SpeechToText();

  bool _speechReady = false;
  bool _isLoading = false;
  bool _obscurePassword = true;
  String? _statusMessage;
  String? _emailFirebaseError;

  static const int _nameMinLength = 2;
  static const int _nameMaxLength = 40;
  static const int _emailMaxLength = 80;
  static const int _passwordMinLength = 6;
  static const int _passwordMaxLength = 30;
  static const int _phoneLength = 10;

  static const Map<String, String> _emailTypoSuggestions = {
    'gmai.com': 'gmail.com',
    'gmial.com': 'gmail.com',
    'gamil.com': 'gmail.com',
    'gmail.con': 'gmail.com',
    'gmail.co': 'gmail.com',
    'hotmai.com': 'hotmail.com',
    'hotmial.com': 'hotmail.com',
    'outlok.com': 'outlook.com',
    'outloo.com': 'outlook.com',
  };

  @override
  void initState() {
    super.initState();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _speak(
        ' إنشاء حساب جديد. أدخلي الإسم والبريد الإلكتروني وكلمة المرور ورقم الجوال',
      );
    });
  }

  Future<void> _speak(String text) async {
    await _flutterTts.setLanguage('ar-SA');
    await _flutterTts.setSpeechRate(0.45);
    await _flutterTts.setPitch(1.0);
    await _flutterTts.speak(text);
  }

  void _showMessageAndSpeak(String message) {
  if (!mounted) return;

  _speak(message);
}

  void _clearStatusMessage() {
    if (_statusMessage == null) return;

    setState(() {
      _statusMessage = null;
    });
  }

  Future<bool> _prepareSpeech() async {
    if (!_speechReady) {
      _speechReady = await _speech.initialize();
    }

    if (!_speechReady) {
      _showMessageAndSpeak('تعذر تشغيل الميكروفون');
    }

    return _speechReady;
  }

  Future<String?> _listenSpeech({
    required String localeId,
    required Duration maxListenTime,
    required Duration silenceTime,
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
      localeId: localeId,
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

  Future<String?> _listenArabic() {
    return _listenSpeech(
      localeId: 'ar_SA',
      maxListenTime: const Duration(seconds: 12),
      silenceTime: const Duration(seconds: 3),
    );
  }

  Future<String?> _listenEnglishLong() {
    return _listenSpeech(
      localeId: 'en_US',
      maxListenTime: const Duration(seconds: 45),
      silenceTime: const Duration(seconds: 5),
    );
  }

  Future<String?> _listenArabicLong() {
    return _listenSpeech(
      localeId: 'ar_SA',
      maxListenTime: const Duration(seconds: 35),
      silenceTime: const Duration(seconds: 4),
    );
  }

  String _spokenEmailToText(String text) {
    return text
        .trim()
        .toLowerCase()
        .replaceAll(' at ', '@')
        .replaceAll(' dot ', '.')
        .replaceAll(' underscore ', '_')
        .replaceAll(' dash ', '-')
        .replaceAll(' hyphen ', '-')
        .replaceAll(' plus ', '+')
        .replaceAll(' ', '');
  }

  String _spokenNumberToDigits(String text) {
    var digits = text
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
        .replaceAll(RegExp(r'[^0-9]'), '');

    if (digits.length == 9 && digits.startsWith('5')) {
      digits = '0$digits';
    }

    return digits;
  }

  bool _isValidEmailFormat(String email) {
    final emailRegex = RegExp(
      r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$',
    );
    return emailRegex.hasMatch(email);
  }

  String? _emailTypoMessage(String email) {
    final parts = email.split('@');
    if (parts.length != 2) return null;

    final suggestion = _emailTypoSuggestions[parts.last];
    if (suggestion == null) return null;

    return 'هل تقصدين $suggestion؟ البريد الإلكتروني يبدو غير صحيح';
  }

  bool _isValidSaudiMobile(String phone) {
    return RegExp(r'^05\d{8}$').hasMatch(phone);
  }

  Future<bool> _isPhoneAlreadyRegistered(String phoneNumber) async {
    final snapshot = await FirebaseFirestore.instance
        .collection('User')
        .where('phoneNumber', isEqualTo: phoneNumber)
        .limit(1)
        .get();

    return snapshot.docs.isNotEmpty;
  }

  String _authErrorMessage(FirebaseAuthException e) {
    switch (e.code) {
      case 'email-already-in-use':
        return 'البريد الإلكتروني مستخدم بالفعل';
      case 'invalid-email':
        return 'البريد الإلكتروني غير صحيح';
      case 'weak-password':
        return 'كلمة المرور ضعيفة جداً';
      case 'operation-not-allowed':
        return 'تسجيل البريد الإلكتروني غير مفعل في Firebase';
      case 'network-request-failed':
        return 'تعذر اتصال التطبيق بالإنترنت';
      case 'too-many-requests':
        return 'تمت محاولات كثيرة. حاولي مرة أخرى لاحقاً';
      default:
        return 'حدث خطأ أثناء إنشاء الحساب';
    }
  }

  String _firestoreErrorMessage(FirebaseException e) {
    switch (e.code) {
      case 'permission-denied':
        return 'تعذر حفظ البيانات في قاعدة البيانات';
      case 'unavailable':
        return 'خدمة قاعدة البيانات غير متاحة حالياً';
      case 'not-found':
        return 'إعدادات قاعدة البيانات غير مكتملة';
      default:
        return 'تم إنشاء الحساب لكن تعذر حفظ بيانات المستخدم';
    }
  }

  String? _validateName(String? value) {
    final name = value?.trim() ?? '';

    if (name.isEmpty) return 'الرجاء إدخال الاسم';
    if (name.length < _nameMinLength) return 'الاسم يجب أن يكون حرفين على الأقل';
    if (name.length > _nameMaxLength) return 'الاسم يجب ألا يتجاوز أربعين حرفاً';

    if (!RegExp(r"^[\u0600-\u06FFa-zA-Z\s'-]+$").hasMatch(name)) {
      return 'الاسم يجب أن يحتوي على حروف فقط';
    }

    return null;
  }

  String? _validateEmail(String? value) {
  final email = value?.trim().toLowerCase() ?? '';

  if (_emailFirebaseError != null) return _emailFirebaseError;

  if (email.isEmpty) return 'الرجاء إدخال البريد الإلكتروني';
    if (email.length > _emailMaxLength) return 'البريد الإلكتروني طويل جداً';
    if (!_isValidEmailFormat(email)) return 'صيغة البريد الإلكتروني غير صحيحة';

    return _emailTypoMessage(email);
  }

  String? _validatePassword(String? value) {
    final password = value ?? '';

    if (password.isEmpty) return 'الرجاء إدخال كلمة المرور';
    if (password.length < _passwordMinLength) {
      return 'كلمة المرور يجب أن تكون ستة أحرف على الأقل';
    }
    if (password.length > _passwordMaxLength) {
      return 'كلمة المرور يجب ألا تتجاوز ثلاثين حرفاً';
    }
    if (password.contains(' ')) return 'كلمة المرور يجب ألا تحتوي على مسافات';

    return null;
  }

  String? _validatePhone(String? value) {
    final phone = value?.trim() ?? '';

    if (phone.isEmpty) return 'الرجاء إدخال رقم الجوال';
    if (!RegExp(r'^\d+$').hasMatch(phone)) return 'رقم الجوال يجب أن يحتوي على أرقام فقط';
    if (!phone.startsWith('05')) return 'رقم الجوال يجب أن يبدأ بـ 05';
    if (phone.length != _phoneLength) return 'رقم الجوال يجب أن يتكون من عشرة أرقام';
    if (!_isValidSaudiMobile(phone)) return 'رقم الجوال غير صحيح';

    return null;
  }

  bool _validateAndSpeakForm() {
    final errors = [
      _validateName(_nameController.text),
      _validateEmail(_emailController.text),
      _validatePassword(_passwordController.text),
      _validatePhone(_phoneController.text),
    ];

    final isValid = _formKey.currentState!.validate();

    final firstError = errors.whereType<String>().firstOrNull;
    if (firstError != null) {
      _showMessageAndSpeak(firstError);
    } else {
      _clearStatusMessage();
    }

    return isValid;
  }

  @override
  void dispose() {
    _speech.stop();
    _flutterTts.stop();
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  Future<void> _signUp() async {
    if (!_validateAndSpeakForm()) return;

    final name = _nameController.text.trim();
    final email = _emailController.text.trim().toLowerCase();
    final password = _passwordController.text.trim();
    final phoneNumber = _phoneController.text.trim();

    setState(() {
      _isLoading = true;
      _statusMessage = null;
    });

    UserCredential? credential;

    try {
      final phoneExists = await _isPhoneAlreadyRegistered(phoneNumber);
      if (phoneExists) {
        _showMessageAndSpeak('رقم الجوال مسجل بالفعل');
        return;
      }

      credential = await FirebaseAuth.instance.createUserWithEmailAndPassword(
        email: email,
        password: password,
      );

      final uid = credential.user!.uid;

      await FirebaseFirestore.instance.collection('User').doc(uid).set({
        'userId': uid,
        'name': name,
        'email': email,
        'phoneNumber': phoneNumber,
        'createdAt': FieldValue.serverTimestamp(),
      });

      if (!mounted) return;

      await _speak('تم إنشاء الحساب بنجاح');
      await Future.delayed(const Duration(seconds: 2));

      if (!mounted) return;

      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const HomePage()),
      );
} on FirebaseAuthException catch (e) {
  if (e.code == 'email-already-in-use') {
    setState(() {
      _emailFirebaseError = 'البريد الإلكتروني مستخدم بالفعل';
    });

    _formKey.currentState!.validate();
    await _speak('البريد الإلكتروني مستخدم بالفعل');
    return;
  }

  _showMessageAndSpeak(_authErrorMessage(e));
} on FirebaseException catch (e) {
      if (credential?.user != null) {
        try {
          await credential!.user!.delete();
        } catch (_) {
          await FirebaseAuth.instance.signOut();
        }
      }

      _showMessageAndSpeak(_firestoreErrorMessage(e));
    } catch (e) {
      _showMessageAndSpeak('حدث خطأ غير متوقع. حاولي مرة أخرى');
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  void _clearOnlyStatusMessage() {
  _clearStatusMessage();
}

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        backgroundColor: Colors.white,
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 20),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 1),
                  const Center(
                    child: Column(
                      children: [
                        Text(
                          'إنشاء حساب جديد',
                          style: TextStyle(
                            fontSize: 42,
                            fontWeight: FontWeight.w900,
                            color: Colors.black,
                          ),
                        ),
                        SizedBox(height: 1),
                        SizedBox(
                          width: 90,
                          child: Divider(
                            thickness: 3,
                            color: burgundy,
                            height: 3,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  const _RequiredLabel('الإسم'),
                  const SizedBox(height: 8),
                  _InputBox(
                    controller: _nameController,
                    hintText: 'أدخلي اسمك ',
                    semanticLabel: 'حقل الاسم',
                    speakMessage: 'أدخلي الإسم',
                    onChanged: (_) => _clearOnlyStatusMessage(),
                    onFieldTap: () => _speak('أدخلي الإسم'),
                    onMicTap: () async {
                      await _speak('قولي الإسم');
                      final text = await _listenArabic();

                      if (text != null) {
                        _nameController.text = text;
                        _clearOnlyStatusMessage();
                      }
                    },
                    maxLength: _nameMaxLength,
                    validator: _validateName,
                  ),
                  const SizedBox(height: 12),
                  const _RequiredLabel('البريد الإلكتروني'),
                  const SizedBox(height: 8),
                  _InputBox(
                    controller: _emailController,
                    hintText: 'example@email.com',
                    semanticLabel: 'حقل البريد الإلكتروني',
                    speakMessage: 'أدخلي البريد الإلكتروني',
                    onChanged: (_) {
  _emailFirebaseError = null;
  _clearOnlyStatusMessage();
},
                    onFieldTap: () => _speak('أدخلي البريد الإلكتروني'),
                    onMicTap: () async {
                      await _speak('قولي البريد الإلكتروني');
                      final text = await _listenEnglishLong();

                      if (text != null) {
                        _emailController.text = _spokenEmailToText(text);
                        _clearOnlyStatusMessage();
                      }
                    },
                    keyboardType: TextInputType.emailAddress,
                    maxLength: _emailMaxLength,
                    inputFormatters: [
                      FilteringTextInputFormatter.deny(RegExp(r'\s')),
                    ],
                    validator: _validateEmail,
                  ),
                  const SizedBox(height: 12),
                  const _RequiredLabel('كلمة المرور'),
                  const SizedBox(height: 8),
                  _InputBox(
                    controller: _passwordController,
                    hintText: 'كلمة المرور',
                    semanticLabel: 'حقل كلمة المرور',
                    speakMessage: 'أدخلي كلمة المرور',
                    onChanged: (_) => _clearOnlyStatusMessage(),
                    onFieldTap: () => _speak('أدخلي كلمة المرور'),
                    obscureText: _obscurePassword,
                    maxLength: _passwordMaxLength,
                    suffixIcon: IconButton(
                      icon: Icon(
                        _obscurePassword ? Icons.visibility_off : Icons.visibility,
                        color: burgundy,
                      ),
                      onPressed: () {
                        setState(() {
                          _obscurePassword = !_obscurePassword;
                        });
                        _speak(
                          _obscurePassword ? 'تم إخفاء كلمة المرور' : 'تم إظهار كلمة المرور',
                        );
                      },
                    ),
                    validator: _validatePassword,
                  ),
                  const SizedBox(height: 12),
                  const _RequiredLabel('رقم الجوال'),
                  const SizedBox(height: 8),
                  _InputBox(
                    controller: _phoneController,
                    hintText: '05XXXXXXXX',
                    semanticLabel: 'حقل رقم الجوال',
                    speakMessage: 'أدخلي رقم الجوال',
                    onChanged: (_) => _clearOnlyStatusMessage(),
                    onFieldTap: () => _speak('أدخلي رقم الجوال'),
                    onMicTap: () async {
                      await _speak('قولي رقم الجوال');
                      final text = await _listenArabicLong();

                      if (text != null) {
                        final digits = _spokenNumberToDigits(text);
                        _phoneController.text = digits.length > _phoneLength
                            ? digits.substring(0, _phoneLength)
                            : digits;
                        _clearOnlyStatusMessage();
                      }
                    },
                    keyboardType: TextInputType.phone,
                    textInputAction: TextInputAction.done,
                    maxLength: _phoneLength,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                    ],
                    validator: _validatePhone,
                  ),
                  if (_statusMessage != null) ...[
                    const SizedBox(height: 16),
                    Text(
                      _statusMessage!,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w900,
                        color: burgundy,
                      ),
                    ),
                  ],
                  const SizedBox(height: 16),
                  Semantics(
                    button: true,
                    label: 'بدء استخدام سنا',
                    hint: 'اضغطي لإنشاء الحساب',
                    child: SizedBox(
                      height: 64,
                      child: ElevatedButton(
                        onPressed: _isLoading ? null : _signUp,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: burgundy,
                          disabledBackgroundColor: burgundy,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14),
                          ),
                          elevation: 0,
                        ),
                        child: _isLoading
                            ? const CircularProgressIndicator(color: Colors.white)
                            : const Text(
                                'بدء استخدام سنا',
                                style: TextStyle(
                                  fontSize: 35,
                                  fontWeight: FontWeight.w900,
                                  color: Colors.white,
                                ),
                              ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _InputBox extends StatelessWidget {
  final TextEditingController controller;
  final String hintText;
  final String semanticLabel;
  final String speakMessage;
  final Future<void> Function()? onMicTap;
  final String? Function(String?)? validator;
  final ValueChanged<String>? onChanged;
  final bool obscureText;
  final TextInputType keyboardType;
  final TextInputAction textInputAction;
  final Widget? suffixIcon;
  final int? maxLength;
  final List<TextInputFormatter>? inputFormatters;
  final VoidCallback? onFieldTap;

  const _InputBox({
    required this.controller,
    required this.hintText,
    required this.semanticLabel,
    required this.speakMessage,
    this.onMicTap,
    this.validator,
    this.onChanged,
    this.obscureText = false,
    this.keyboardType = TextInputType.text,
    this.textInputAction = TextInputAction.next,
    this.suffixIcon,
    this.maxLength,
    this.inputFormatters,
    this.onFieldTap,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticLabel,
      hint: speakMessage,
      textField: true,
      child: TextFormField(
        controller: controller,
        autovalidateMode: AutovalidateMode.onUserInteraction,
        obscureText: obscureText,
        keyboardType: keyboardType,
        textInputAction: textInputAction,
        textAlign: TextAlign.right,
        onTap: onFieldTap,
        onChanged: onChanged,
        maxLength: maxLength,
        inputFormatters: inputFormatters,
        style: const TextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w700,
          color: Colors.black,
        ),
        decoration: InputDecoration(
          counterText: '',
          hintText: hintText,
          suffixIcon: suffixIcon ??
              (onMicTap == null
                  ? null
                  : IconButton(
                      tooltip: 'إملاء صوتي',
                      icon: const Icon(
                        Icons.mic_none_outlined,
                        color: Color(0xFF640000),
                        size: 30,
                      ),
                      onPressed: onMicTap,
                    )),
          hintStyle: const TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.w700,
            color: Color(0xFF6F6F6F),
          ),
          errorStyle: const TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w800,
            color: Color(0xFFB00020),
          ),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 18,
          ),
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Colors.black, width: 1.5),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Colors.black, width: 1.5),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Colors.black, width: 2),
          ),
          errorBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Color(0xFFB00020), width: 2),
          ),
          focusedErrorBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Color(0xFFB00020), width: 2),
          ),
        ),
        validator: validator,
      ),
    );
  }
}

class _RequiredLabel extends StatelessWidget {
  final String text;

  const _RequiredLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return RichText(
      textAlign: TextAlign.right,
      text: TextSpan(
        children: [
          TextSpan(
            text: text,
            style: const TextStyle(
              fontSize: 30,
              fontWeight: FontWeight.w900,
              color: Colors.black,
            ),
          ),
          const TextSpan(
            text: ' *',
            style: TextStyle(
              fontSize: 30,
              fontWeight: FontWeight.w900,
              color: Color(0xFF640000),
            ),
          ),
        ],
      ),
    );
  }
}