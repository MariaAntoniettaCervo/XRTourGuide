from rest_framework import serializers
from .models import Tour, Review, Waypoint, WaypointViewImage
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.urls import reverse

class WaypointViewImageSerializer(serializers.ModelSerializer):
    image_name = serializers.SerializerMethodField()

    class Meta:
        model = WaypointViewImage
        fields = ['waypoint', 'image_name']

    def get_image_name(self, obj):
        return obj.image.name if obj.image else None
        
class WaypointSerializer(serializers.ModelSerializer):
    images = WaypointViewImageSerializer(many=True, read_only=True)
    lat = serializers.SerializerMethodField()
    lon = serializers.SerializerMethodField()

    isPreliminaryInfo = serializers.BooleanField(
        source="is_preliminary_info",
        read_only=True
    )

    class Meta:
        model = Waypoint
        fields = [
            'title', 'coordinates', 'tour', 'description',
            'images', 'lat', 'lon', 'id', 'position', "is_preliminary_info", "isPreliminaryInfo"
        ]

    def get_lat(self, obj):
        if not obj.coordinates:
            return None
        return float(obj.coordinates.split(',')[0])
    
    def get_lon(self, obj):
        if not obj.coordinates:
            return None
        return float(obj.coordinates.split(',')[1])
    
    def get_pdf_name(self, obj):
        return obj.pdf_item.name if obj.pdf_item else None

    def get_readme_name(self, obj):
        return obj.readme_item.name if obj.readme_item else None

    def get_video_name(self, obj):
        return obj.video_item.name if obj.video_item else None

    def get_audio_name(self, obj):
        return obj.audio_item.name if obj.audio_item else None
    
class TourSerializer(serializers.ModelSerializer):
    creation_time = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    default_img = serializers.SerializerMethodField()
    lat = serializers.SerializerMethodField()
    lon = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    l_edited = serializers.SerializerMethodField()
    rating_counter = serializers.SerializerMethodField()
    class Meta:
        model = Tour
        fields = ['title', 'subtitle', 'place', 'category', 'language', 'description', 'user', 'lat', 'lon', 'default_img', 'creation_time', 'user_name', 'id', 'tot_view', 'l_edited', 'rating', 'rating_counter', 'status']


    def get_rating_counter(self, obj):
        if len(obj.reviews.all()) == 0:
            return 0
        return int(len(obj.reviews.all()))

    def get_l_edited(self, obj):
        return obj.last_edited.strftime("%Y-%m-%d")
    
    def get_rating(self, obj):
        if len(obj.reviews.all()) == 0:
            return 0.0
        return float(sum([review.rating for review in obj.reviews.all()])) / float(len(obj.reviews.all()))

        
    def get_lat(self, obj):
        if len(obj.coordinates) > 0:
            return float(obj.coordinates.split(',')[0])
        return None
    
    def get_lon(self, obj):
        if len(obj.coordinates) > 0:
            return float(obj.coordinates.split(',')[1])
        return None
    
    def get_default_img(self, obj):
        return obj.default_image.name if obj.default_image else None
    
    def get_creation_time(self, obj):
        return obj.creation_time.strftime("%Y-%m-%d")
    
    def get_user_name(self, obj):
        return obj.user.username
    
class UserSerializer(serializers.ModelSerializer):
    review_count = serializers.SerializerMethodField()
    class Meta:
        model = get_user_model()
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'city', 'description', 'review_count']
    
    def get_review_count(self, obj):
        return len(obj.reviews.all())

class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    creation_date = serializers.SerializerMethodField()
    class Meta:
        model = Review
        fields = ['tour', 'user', 'rating', 'comment', 'user_name', 'creation_date', 'id']
    
    def get_user_name(self, obj):
        return obj.user.username
    
    def get_creation_date(self, obj):
        return obj.timestamp.strftime("%Y-%m-%d")
    
# class RegisterSerializer(serializers.ModelSerializer):
#     password = serializers.CharField(write_only=True)

#     class Meta:
#         model = get_user_model()
#         fields = ['username', 'email', 'password', 'first_name', 'last_name', 'city', 'description']

#     def validate_email(self, value):
#         if get_user_model().objects.filter(email=value).exists():
#             raise serializers.ValidationError("Questo indirizzo email è già in uso.")
#         return value
    
#     def create(self, validated_data):
#         user = get_user_model().objects.create_user(
#             username=validated_data['username'],
#             email=validated_data['email'],
#             password=validated_data['password'],
#             first_name=validated_data['first_name'],
#             last_name=validated_data['last_name'],
#             city=validated_data['city'],
#             description=validated_data['description'],
#             is_active=False,
#             is_staff = True
#         )
        
#         try:
#             user_group = Group.objects.get(name="User")
#             user.groups.add(user_group)
#         except Group.DoesNotExist:
#             raise serializers.ValidationError("Il gruppo 'User' non esiste.")
        
#         return user

# class PasswordResetSerializer(serializers.Serializer):
#     email = serializers.EmailField()

#     def validate_email(self, value):
#         if not get_user_model().objects.filter(email=value).exists():
#             raise serializers.ValidationError("Email non trovata.")
#         return value

#     def save(self):
#         email = self.validated_data['email']
#         user = get_user_model().objects.get(email=email)
#         token = default_token_generator.make_token(user)
#         uid = urlsafe_base64_encode(force_bytes(user.pk))

#         reset_link = self.context['request'].build_absolute_uri(
#             reverse('reset-password-confirm-page', kwargs={'uidb64': uid, 'token': token})
#         )

#         subject = "Password Reset Request"
#         message = f"Clicca sul link per resettare la tua password: {reset_link}"
        
#         send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])


# class PasswordResetConfirmSerializer(serializers.Serializer):
#     uidb64 = serializers.CharField()
#     token = serializers.CharField()
#     new_password = serializers.CharField(min_length=8)

#     def validate(self, attrs):
#         try:
#             uid = urlsafe_base64_decode(attrs['uidb64']).decode()
#             user = get_user_model().objects.get(pk=uid)
#         except Exception:
#             raise serializers.ValidationError("Link non valido.")

#         if not default_token_generator.check_token(user, attrs['token']):
#             raise serializers.ValidationError("Token non valido o scaduto.")

#         attrs['user'] = user
#         return attrs

#     def save(self, **kwargs):
#         user = self.validated_data['user']
#         new_password = self.validated_data['new_password']
#         user.set_password(new_password)
#         user.save()
