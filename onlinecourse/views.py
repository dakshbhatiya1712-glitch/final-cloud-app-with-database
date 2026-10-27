
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.db.models import Q
import logging

from .models import (
    Course,
    Enrollment,
    Question,
    Choice,
    Submission,
)

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}

    if request.method == "GET":
        return render(
            request,
            "onlinecourse/user_registration_bootstrap.html",
            context
        )

    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["psw"]
        first_name = request.POST["firstname"]
        last_name = request.POST["lastname"]

        user_exist = User.objects.filter(username=username).exists()

        if not user_exist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            login(request, user)
            return redirect("onlinecourse:index")

        context["message"] = "User already exists."
        return render(
            request,
            "onlinecourse/user_registration_bootstrap.html",
            context
        )


def login_request(request):
    context = {}

    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["psw"]
        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("onlinecourse:index")

        context["message"] = "Invalid username or password."
        return render(
            request,
            "onlinecourse/user_login_bootstrap.html",
            context
        )

    return render(
        request,
        "onlinecourse/user_login_bootstrap.html",
        context
    )


def logout_request(request):
    logout(request)
    return redirect("onlinecourse:index")


def check_if_enrolled(user, course):
    if not user.is_authenticated:
        return False

    return Enrollment.objects.filter(
        user=user,
        course=course
    ).exists()


class CourseListView(generic.ListView):
    template_name = "onlinecourse/course_list_bootstrap.html"
    context_object_name = "course_list"

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by("-total_enrollment")[:10]

        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = "onlinecourse/course_detail_bootstrap.html"


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    if user.is_authenticated:
        is_enrolled = check_if_enrolled(user, course)

        if not is_enrolled:
            Enrollment.objects.create(
                user=user,
                course=course,
                mode="honor"
            )
            course.total_enrollment += 1
            course.save()

    return HttpResponseRedirect(
        reverse(
            viewname="onlinecourse:course_details",
            args=(course.id,)
        )
    )


def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith("choice"):
            try:
                choice_id = int(request.POST[key])
                submitted_answers.append(choice_id)
            except (ValueError, TypeError):
                continue

    return submitted_answers


def submit(request, course_id):
    if not request.user.is_authenticated:
        return redirect("onlinecourse:login")

    if request.method != "POST":
        return redirect(
            "onlinecourse:course_details",
            course_id=course_id
        )

    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    submission = Submission.objects.create(
        enrollment=enrollment
    )

    answer_ids = extract_answers(request)

    for choice in Choice.objects.filter(id__in=answer_ids):
        submission.choices.add(choice)

    return redirect(
        "onlinecourse:show_exam_result",
        course_id=course.id,
        submission_id=submission.id
    )


def show_exam_result(request, course_id, submission_id):
    if not request.user.is_authenticated:
        return redirect("onlinecourse:login")

    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__user=request.user,
        enrollment__course=course
    )

    selected_ids = set(
        submission.choices.values_list("id", flat=True)
    )

    questions = Question.objects.filter(
        lesson__course=course
    ).prefetch_related("choice_set")

    question_results = []
    total_score = 0
    max_score = 0

    for question in questions:
        max_score += question.grade

        correct_ids = set(
            question.choice_set.filter(
                is_correct=True
            ).values_list("id", flat=True)
        )

        selected_for_question = set(
            question.choice_set.filter(
                id__in=selected_ids
            ).values_list("id", flat=True)
        )

        is_correct = (
            bool(correct_ids)
            and correct_ids == selected_for_question
        )

        earned_grade = question.grade if is_correct else 0
        total_score += earned_grade

        question_results.append({
            "question": question,
            "is_correct": is_correct,
            "grade": earned_grade,
            "selected_ids": selected_ids,
        })

    context = {
        "course": course,
        "submission": submission,
        "question_results": question_results,
        "total_score": total_score,
        "max_score": max_score,
        "passed": total_score >= (max_score * 0.5),
    }

    return render(
        request,
        "onlinecourse/exam_result_bootstrap.html",
        context
    )
