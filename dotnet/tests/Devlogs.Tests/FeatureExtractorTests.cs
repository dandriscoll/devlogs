using Devlogs.Formatting;
using Xunit;

namespace Devlogs.Tests;

public class FeatureExtractorTests
{
    [Fact]
    public void ExtractFeatures_WithNull_ReturnsNull()
    {
        // Act
        var result = FeatureExtractor.ExtractFeatures(null);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ExtractFeatures_WithoutFeaturesProperty_ReturnsNull()
    {
        // Arrange
        var state = new { user = "alice", count = 42 };

        // Act
        var result = FeatureExtractor.ExtractFeatures(state);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ExtractFeatures_WithFeaturesProperty_ExtractsValues()
    {
        // Arrange
        var state = new
        {
            features = new Dictionary<string, object>
            {
                ["user_id"] = 42,
                ["username"] = "alice",
                ["is_premium"] = true
            }
        };

        // Act
        var result = FeatureExtractor.ExtractFeatures(state);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Count);
        Assert.Equal(42, result["user_id"]);
        Assert.Equal("alice", result["username"]);
        Assert.Equal(true, result["is_premium"]);
    }

    [Fact]
    public void ExtractFeatures_WithCapitalFeaturesProperty_ExtractsValues()
    {
        // Arrange
        var state = new
        {
            Features = new Dictionary<string, object>
            {
                ["user_id"] = 42
            }
        };

        // Act
        var result = FeatureExtractor.ExtractFeatures(state);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(42, result["user_id"]);
    }

    [Fact]
    public void ExtractFeatures_WithPrimitiveTypes_PreservesTypes()
    {
        // Arrange
        var state = new
        {
            features = new Dictionary<string, object>
            {
                ["string_val"] = "test",
                ["int_val"] = 42,
                ["long_val"] = 123L,
                ["float_val"] = 3.14f,
                ["double_val"] = 2.71,
                ["bool_val"] = true,
                ["null_val"] = (object?)null
            }
        };

        // Act
        var result = FeatureExtractor.ExtractFeatures(state);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("test", result["string_val"]);
        Assert.Equal(42, result["int_val"]);
        Assert.Equal(123L, result["long_val"]);
        Assert.Equal(3.14f, result["float_val"]);
        Assert.Equal(2.71, result["double_val"]);
        Assert.Equal(true, result["bool_val"]);
        Assert.Null(result["null_val"]);
    }

    [Fact]
    public void ExtractFeatures_WithComplexTypes_StringifiesThem()
    {
        // Arrange
        var complexObject = new { Name = "Test", Value = 42 };
        var state = new
        {
            features = new Dictionary<string, object>
            {
                ["complex"] = complexObject
            }
        };

        // Act
        var result = FeatureExtractor.ExtractFeatures(state);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<string>(result["complex"]);
    }

    [Fact]
    public void ExtractFeatures_SkipsNullOrEmptyKeys()
    {
        // Arrange
        var state = new
        {
            features = new Dictionary<string, object?>
            {
                ["valid"] = "value",
                ["  "] = "whitespace",
                [""] = "empty"
            }
        };

        // Act
        var result = FeatureExtractor.ExtractFeatures(state);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result);
        Assert.Equal("value", result["valid"]);
    }
}
