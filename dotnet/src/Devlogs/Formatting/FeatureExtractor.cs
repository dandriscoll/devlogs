using System.Collections;

namespace Devlogs.Formatting;

/// <summary>
/// Extracts and normalizes features from log state.
/// </summary>
internal static class FeatureExtractor
{
    private static readonly Type[] PrimitiveTypes =
    {
        typeof(string),
        typeof(int), typeof(long), typeof(short), typeof(byte),
        typeof(uint), typeof(ulong), typeof(ushort), typeof(sbyte),
        typeof(float), typeof(double), typeof(decimal),
        typeof(bool)
    };

    /// <summary>
    /// Extracts features from log state object.
    /// </summary>
    public static Dictionary<string, object?>? ExtractFeatures(object? state)
    {
        if (state == null)
            return null;

        // Try to find "features" property in state
        var stateType = state.GetType();
        var featuresProperty = stateType.GetProperty("features")
            ?? stateType.GetProperty("Features");

        if (featuresProperty != null)
        {
            var featuresValue = featuresProperty.GetValue(state);
            return NormalizeFeatures(featuresValue);
        }

        // Check if state itself is IEnumerable<KeyValuePair<string, object>>
        if (state is IEnumerable<KeyValuePair<string, object>> enumerable)
        {
            var dict = enumerable.ToDictionary(kvp => kvp.Key, kvp => kvp.Value);
            if (dict.ContainsKey("features") || dict.ContainsKey("Features"))
            {
                var key = dict.ContainsKey("features") ? "features" : "Features";
                return NormalizeFeatures(dict[key]);
            }
        }

        return null;
    }

    /// <summary>
    /// Normalizes feature values to supported types.
    /// </summary>
    private static Dictionary<string, object?>? NormalizeFeatures(object? value)
    {
        if (value == null)
            return null;

        var result = new Dictionary<string, object?>();

        // Handle IDictionary<string, object>
        if (value is IDictionary<string, object> dict)
        {
            foreach (var kvp in dict)
            {
                var key = kvp.Key?.Trim();
                if (string.IsNullOrEmpty(key))
                    continue;

                result[key] = CoerceFeatureValue(kvp.Value);
            }
        }
        // Handle IEnumerable<KeyValuePair<string, object>>
        else if (value is IEnumerable enumerable)
        {
            foreach (var item in enumerable)
            {
                if (item is KeyValuePair<string, object> kvp)
                {
                    var key = kvp.Key?.Trim();
                    if (string.IsNullOrEmpty(key))
                        continue;

                    result[key] = CoerceFeatureValue(kvp.Value);
                }
                else if (item is DictionaryEntry entry && entry.Key is string strKey)
                {
                    var key = strKey.Trim();
                    if (string.IsNullOrEmpty(key))
                        continue;

                    result[key] = CoerceFeatureValue(entry.Value);
                }
            }
        }

        return result.Count > 0 ? result : null;
    }

    /// <summary>
    /// Coerces a feature value to a supported type.
    /// </summary>
    private static object? CoerceFeatureValue(object? value)
    {
        if (value == null)
            return null;

        var valueType = value.GetType();

        // Keep primitive types as-is
        if (IsPrimitiveType(valueType))
            return value;

        // Stringify complex types
        return value.ToString();
    }

    private static bool IsPrimitiveType(Type type)
    {
        if (type == null)
            return false;

        if (PrimitiveTypes.Contains(type))
            return true;

        // Handle nullable types
        var underlyingType = Nullable.GetUnderlyingType(type);
        if (underlyingType != null)
            return IsPrimitiveType(underlyingType);

        return false;
    }
}
