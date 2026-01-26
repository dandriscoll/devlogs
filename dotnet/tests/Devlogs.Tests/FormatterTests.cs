using Microsoft.Extensions.Logging;
using Devlogs.Context;
using Devlogs.Configuration;
using Devlogs.Formatting;
using Xunit;

namespace Devlogs.Tests;

public class FormatterTests
{
    private static DevlogsOptions CreateTestOptions(
        string application = "test-app",
        string component = "test-component",
        string? environment = null,
        string? version = null)
    {
        return new DevlogsOptions
        {
            Application = application,
            Component = component,
            Environment = environment,
            Version = version
        };
    }

    [Fact]
    public void FormatLogDocument_IncludesBasicFields()
    {
        // Arrange
        var context = new DevlogsContext();
        var options = CreateTestOptions();
        var formatter = new LogDocumentFormatter(context, options);

        // Act
        var document = formatter.FormatLogDocument(
            LogLevel.Information,
            new EventId(1, "TestEvent"),
            "Test state",
            null,
            (state, ex) => state?.ToString() ?? string.Empty,
            "TestCategory");

        // Assert
        Assert.Equal("log_entry", document["doc_type"]);
        Assert.Equal("test-app", document["application"]);
        Assert.Equal("test-component", document["component"]);
        Assert.Equal("info", document["level"]);
        Assert.Equal("Test state", document["message"]);
        Assert.NotNull(document["timestamp"]);
        Assert.True(document["timestamp"]?.ToString()?.EndsWith("Z"));
    }

    [Fact]
    public void FormatLogDocument_IncludesSourceObject()
    {
        // Arrange
        var context = new DevlogsContext();
        var options = CreateTestOptions();
        var formatter = new LogDocumentFormatter(context, options);

        // Act
        var document = formatter.FormatLogDocument(
            LogLevel.Information,
            new EventId(1),
            "Test",
            null,
            (state, ex) => state?.ToString() ?? string.Empty,
            "TestCategory");

        // Assert
        Assert.NotNull(document["source"]);
        var source = document["source"] as Dictionary<string, object?>;
        Assert.NotNull(source);
        Assert.Equal("TestCategory", source["logger"]);
    }

    [Fact]
    public void FormatLogDocument_IncludesProcessObject()
    {
        // Arrange
        var context = new DevlogsContext();
        var options = CreateTestOptions();
        var formatter = new LogDocumentFormatter(context, options);

        // Act
        var document = formatter.FormatLogDocument(
            LogLevel.Information,
            new EventId(1),
            "Test",
            null,
            (state, ex) => state?.ToString() ?? string.Empty,
            "TestCategory");

        // Assert
        Assert.NotNull(document["process"]);
        var process = document["process"] as Dictionary<string, object?>;
        Assert.NotNull(process);
        Assert.True((int?)process["id"] > 0);
        Assert.True((int?)process["thread"] > 0);
    }

    [Fact]
    public void FormatLogDocument_IncludesContextValues()
    {
        // Arrange
        var context = new DevlogsContext();
        var options = CreateTestOptions();
        var formatter = new LogDocumentFormatter(context, options);

        // Act
        using (context.BeginOperation("test-op-123", "test-area"))
        {
            var document = formatter.FormatLogDocument(
                LogLevel.Information,
                new EventId(1),
                "Test",
                null,
                (state, ex) => state?.ToString() ?? string.Empty,
                "TestCategory");

            // Assert
            Assert.Equal("test-op-123", document["operation_id"]);
            Assert.Equal("test-area", document["area"]);
        }
    }

    [Fact]
    public void FormatLogDocument_IncludesOptionalMetadata()
    {
        // Arrange
        var context = new DevlogsContext();
        var options = CreateTestOptions(
            environment: "production",
            version: "1.2.3");
        var formatter = new LogDocumentFormatter(context, options);

        // Act
        var document = formatter.FormatLogDocument(
            LogLevel.Information,
            new EventId(1),
            "Test",
            null,
            (state, ex) => state?.ToString() ?? string.Empty,
            "TestCategory");

        // Assert
        Assert.Equal("production", document["environment"]);
        Assert.Equal("1.2.3", document["version"]);
    }

    [Fact]
    public void FormatLogDocument_IncludesException()
    {
        // Arrange
        var context = new DevlogsContext();
        var options = CreateTestOptions();
        var formatter = new LogDocumentFormatter(context, options);
        var exception = new InvalidOperationException("Test exception");

        // Act
        var document = formatter.FormatLogDocument(
            LogLevel.Error,
            new EventId(1),
            "Test",
            exception,
            (state, ex) => $"{state}: {ex?.Message}",
            "TestCategory");

        // Assert
        Assert.NotNull(document["exception"]);
        Assert.Contains("Test exception", document["exception"]?.ToString());
    }

    [Fact]
    public void FormatLogDocument_NormalizesLogLevels()
    {
        // Arrange
        var context = new DevlogsContext();
        var options = CreateTestOptions();
        var formatter = new LogDocumentFormatter(context, options);

        var testCases = new Dictionary<LogLevel, string>
        {
            { LogLevel.Trace, "trace" },
            { LogLevel.Debug, "debug" },
            { LogLevel.Information, "info" },
            { LogLevel.Warning, "warning" },
            { LogLevel.Error, "error" },
            { LogLevel.Critical, "critical" }
        };

        // Act & Assert
        foreach (var testCase in testCases)
        {
            var document = formatter.FormatLogDocument(
                testCase.Key,
                new EventId(1),
                "Test",
                null,
                (state, ex) => state?.ToString() ?? string.Empty,
                "TestCategory");

            Assert.Equal(testCase.Value, document["level"]);
        }
    }
}
