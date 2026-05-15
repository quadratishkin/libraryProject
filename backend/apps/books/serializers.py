from rest_framework import serializers

from apps.books.models import TermDefinition, UserBook, UserTermEdit


class UserBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserBook
        fields = (
            "id",
            "title",
            "authors",
            "original_filename",
            "file_hash",
            "status",
            "error_message",
            "is_protected",
            "views_count",
            "uploaded_at",
            "processed_at",
        )


class UserBookDetailSerializer(UserBookSerializer):
    terms_count = serializers.SerializerMethodField()

    class Meta(UserBookSerializer.Meta):
        fields = UserBookSerializer.Meta.fields + ("terms_count",)

    def get_terms_count(self, obj):
        if not obj.global_cache_id:
            return 0
        return obj.global_cache.terms.count()


class TermDefinitionSerializer(serializers.ModelSerializer):
    effective_definition = serializers.SerializerMethodField()
    custom_definition = serializers.SerializerMethodField()

    class Meta:
        model = TermDefinition
        fields = (
            "id",
            "term",
            "normalized_term",
            "definition",
            "effective_definition",
            "custom_definition",
            "source_chapter",
            "source_paragraph_index",
            "source_quote",
            "frequency",
        )

    def _edits_map(self) -> dict[int, UserTermEdit]:
        return self.context.get("edits_map", {})

    def get_custom_definition(self, obj):
        edit = self._edits_map().get(obj.id)
        return edit.custom_definition if edit else None

    def get_effective_definition(self, obj):
        edit = self._edits_map().get(obj.id)
        return edit.custom_definition if edit else obj.definition


class UserTermEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserTermEdit
        fields = ("id", "custom_definition", "updated_at")
        read_only_fields = ("id", "updated_at")

    def validate_custom_definition(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Определение не может быть пустым.")
        return value
