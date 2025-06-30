from django.http import HttpResponse
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib import messages

class CustomUserForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].help_text = "Max 150 characters. No Spaces"
    email = forms.EmailField(required=True)
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


# Create your views here.
def register(request):
    if request.method == 'POST':
        form = CustomUserForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, "You have registered successfully!")
            return redirect("login")
        else:
            messages.error(request, "Invalid creditials")

    else:
        form = CustomUserForm()   
            
    return render(request, "myrai/register.html", {'form': form})

def login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("username")

        user = authenticate(request, username=username, password=password)

        if not None:
            login.user(request, user)
            messages.success(request, f"{username}, Welcome back!")
            return redirect("index")
        
        else:
            messages.error(request, "Try logging in again")

    return render(request, "myrai/login.html")


def index(request):
    return render(request, "myrai/index.html")

def about(request):
    return render(request, "myrai/about.html")

def contact(request):
    return render(request, "myrai/contact.html")

def services(request):
    return render(request, "myrai/services.html")


