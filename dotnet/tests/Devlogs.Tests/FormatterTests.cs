using Microsoft.Extensions.Logging;
using Devlogs.Context;
using Devlogs.Formatting;
using Xunit;

namespace Devlogs.Tests;

public class FormatterTests
{
    [Fact]
    public void FormatLogDocument_IncludesBasicFields()
    {
        // Arrange
        var context = new DevlogsContext();
        var formatter = new LogDocumentFormatter(context);

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
        Assert.Equal("info", document["level"]);
        Assert.Equal(2, document["levelno"]); // Information = 2
        Assert.Equal("TestCategory", document["logger_name"]);
        Assert.Equal("Test state", document["message"]);
        Assert.NotNull(document["timestamp"]);
        Assert.True(document["timestamp"]?.ToString()?.EndsWith("Z"));
    }

    [Fact]
    public void FormatLogDocument_IncludesContextValues()
    {
        // Arrange
        var context = new DevlogsContext();
        var formatter = new LogDocumentFormatter(context);

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
    public void FormatLogDocument_IncludesException()
    {
        // Arrange
        var context = new DevlogsContext();
        var formatter = new LogDocumentFormatter(context);
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
        var formatter = new LogDocumentFormatter(context);

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
